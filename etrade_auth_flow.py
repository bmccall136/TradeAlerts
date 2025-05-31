import os
import json
import webbrowser
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv, set_key, dotenv_values

# -------------------------------------------------------------------
# STEP 1: Load existing .env so we can update it in-place
# -------------------------------------------------------------------
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(ENV_PATH)

# Names of the variables we want to update
KEY_OAUTH_TOKEN = 'OAUTH_TOKEN'
KEY_OAUTH_TOKEN_SECRET = 'OAUTH_TOKEN_SECRET'

# -------------------------------------------------------------------
# STEP 2: Read consumer key/secret from .env
# -------------------------------------------------------------------
CONSUMER_KEY    = os.getenv("ETRADE_API_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_API_SECRET")

if not CONSUMER_KEY or not CONSUMER_SECRET:
    print("⚠️  You must have ETRADE_API_KEY and ETRADE_API_SECRET in your .env first.")
    exit(1)

# -------------------------------------------------------------------
# STEP 3: Define E*TRADE OAuth endpoints
# -------------------------------------------------------------------
BASE_URL           = "https://api.etrade.com"
REQUEST_TOKEN_URL  = f"{BASE_URL}/oauth/request_token"
ACCESS_TOKEN_URL   = f"{BASE_URL}/oauth/access_token"
AUTHORIZE_URL      = "https://us.etrade.com/e/t/etws/authorize"
TOKEN_FILE         = "etrade_tokens.json"

# -------------------------------------------------------------------
# STEP 4: Get a Request Token
# -------------------------------------------------------------------
oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri="oob")
try:
    fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
except Exception as e:
    print(f"❌ Failed to fetch request token: {e}")
    exit(1)

resource_owner_key    = fetch_response.get("oauth_token")
resource_owner_secret = fetch_response.get("oauth_token_secret")

# -------------------------------------------------------------------
# STEP 5: Direct user to authorize in browser
# -------------------------------------------------------------------
auth_url = f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}"
print("\n🔑 Opening browser to authorize E*TRADE access…")
print(f"👉 If nothing opens automatically, visit this URL:\n{auth_url}\n")
webbrowser.open(auth_url)

# -------------------------------------------------------------------
# STEP 6: Prompt for the PIN/verifier
# -------------------------------------------------------------------
verifier = input("Enter the PIN (verifier) from E*TRADE: ").strip()

# -------------------------------------------------------------------
# STEP 7: Exchange Request Token + Verifier for Access Token
# -------------------------------------------------------------------
oauth = OAuth1Session(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier
)
try:
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
except Exception as e:
    print(f"❌ Failed to fetch access token: {e}")
    exit(1)

access_token        = tokens.get("oauth_token")
access_token_secret = tokens.get("oauth_token_secret")

if not access_token or not access_token_secret:
    print("❌ Received invalid tokens from E*TRADE.")
    exit(1)

# -------------------------------------------------------------------
# STEP 8: Persist new tokens into .env
# -------------------------------------------------------------------
# Use python-dotenv's set_key to overwrite (or append) these entries in .env
set_key(ENV_PATH, KEY_OAUTH_TOKEN,        access_token)
set_key(ENV_PATH, KEY_OAUTH_TOKEN_SECRET, access_token_secret)

# (Optional) Also save a backup JSON file containing the raw response
with open(TOKEN_FILE, "w") as f:
    json.dump(tokens, f, indent=2)

print("\n✅ OAuth tokens saved into .env:")
print(f"   {KEY_OAUTH_TOKEN}        = {access_token}")
print(f"   {KEY_OAUTH_TOKEN_SECRET} = {access_token_secret}")
print(f"\n🔒 A copy was also written to {TOKEN_FILE} for backup.\n")
