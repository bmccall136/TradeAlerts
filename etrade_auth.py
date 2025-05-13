import os
import json
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

# Load environment variables from .env
load_dotenv('.env')

# Accept multiple env var names for credentials
CONSUMER_KEY    = os.getenv('ETRADE_CONSUMER_KEY') or os.getenv('ETRADE_API_KEY') or os.getenv('CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('ETRADE_CONSUMER_SECRET') or os.getenv('ETRADE_API_SECRET') or os.getenv('CONSUMER_SECRET')
ACCESS_TOKEN    = os.getenv('OAUTH_TOKEN') or os.getenv('ETRADE_ACCESS_TOKEN')
ACCESS_SECRET   = os.getenv('OAUTH_TOKEN_SECRET') or os.getenv('ETRADE_ACCESS_SECRET')

# Fallback to tokens JSON if missing
if not ACCESS_TOKEN or not ACCESS_SECRET:
    try:
        with open('etrade_tokens.json') as f:
            tokens = json.load(f)
            ACCESS_TOKEN = tokens.get('oauth_token') or ACCESS_TOKEN
            ACCESS_SECRET = tokens.get('oauth_token_secret') or ACCESS_SECRET
            print("Loaded OAuth tokens from etrade_tokens.json")
    except FileNotFoundError:
        pass

# Final credential check
missing = [name for name, val in [
    ("consumer key", CONSUMER_KEY),
    ("consumer secret", CONSUMER_SECRET),
    ("access token", ACCESS_TOKEN),
    ("access secret", ACCESS_SECRET)
] if not val]
if missing:
    raise ValueError(f"Missing E*TRADE credentials in .env or etrade_tokens.json: {', '.join(missing)}")

def get_etrade_session():
    return OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=ACCESS_TOKEN,
        resource_owner_secret=ACCESS_SECRET
    )
