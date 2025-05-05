import os
import requests
from dotenv import load_dotenv
from authlib.integrations.requests_client import OAuth1Session

# Load .env
load_dotenv()

# Load credentials
consumer_key = os.getenv("ETRADE_API_KEY")
consumer_secret = os.getenv("ETRADE_API_SECRET")
oauth_token = os.getenv("OAUTH_TOKEN")
oauth_token_secret = os.getenv("OAUTH_TOKEN_SECRET")

print(f"Consumer Key: {consumer_key}")
print(f"Consumer Secret: {consumer_secret}")
print(f"OAuth Token: {oauth_token}")
print(f"OAuth Token Secret: {oauth_token_secret}")

if not all([consumer_key, consumer_secret, oauth_token, oauth_token_secret]):
    print("\n❌ Missing credentials. Please reauthenticate.")
    exit(1)

try:
    session = OAuth1Session(
        client_id=consumer_key,
        client_secret=consumer_secret,
        token=oauth_token,
        token_secret=oauth_token_secret,
    )

    response = session.get("https://api.etrade.com/v1/accounts/list.json")

    if response.status_code == 200:
        print("\n✅ API connection successful!")
    else:
        print(f"\n⚠️ API connection failed. Status code: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"\n❌ Error: {str(e)}")
    exit(1)
