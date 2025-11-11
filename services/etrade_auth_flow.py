"""
services/etrade_auth_flow.py

Helper for E*TRADE OAuth 1.0a (PIN / oob flow).

Used by:
    from .etrade_auth_flow import get_oauth_session

Behavior:
- Reads API keys from etrade.env in the project root.
- Uses etrade_tokens.json in the project root to store access tokens.
- If tokens are missing, running this module directly will walk you
  through the PIN flow and save fresh tokens.
"""

import os
import json
from pathlib import Path

from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

# ----- Paths -----
BASE_DIR = Path(__file__).resolve().parents[1]  # C:\TradeAlerts
ENV_PATH = BASE_DIR / "etrade.env"
TOKEN_PATH = BASE_DIR / "etrade_tokens.json"

# ----- Load env -----
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

CONSUMER_KEY = (
    os.getenv("ETRADE_API_KEY")
    or os.getenv("ETRADE_CONSUMER_KEY")
)
CONSUMER_SECRET = (
    os.getenv("ETRADE_API_SECRET")
    or os.getenv("ETRADE_CONSUMER_SECRET")
)

REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"


# ----- Internal helpers -----
def _require_keys():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        raise RuntimeError(
            "E*TRADE API keys not found. Set ETRADE_API_KEY and "
            "ETRADE_API_SECRET in etrade.env at the project root."
        )


def _load_tokens():
    if TOKEN_PATH.exists():
        with TOKEN_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "oauth_token" in data and "oauth_token_secret" in data:
            return data
    return None


def _save_tokens(tokens: dict):
    TOKEN_PATH.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


# ----- Public helpers -----
def start_pin_flow() -> dict:
    """
    Run the PIN (oob) OAuth flow and persist new access tokens.

    Run manually (python -m services.etrade_auth_flow) whenever you
    need to (re)authorize.
    """
    _require_keys()

    # Step 1: request token
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri="oob",
    )
    tmp = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    resource_owner_key = tmp["oauth_token"]
    resource_owner_secret = tmp["oauth_token_secret"]

    # Step 2: direct user to authorize
    auth_url = f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}"
    print("\n🔑 Open this URL in a browser and sign in to E*TRADE:")
    print(auth_url)

    pin = input("\nEnter the PIN shown by E*TRADE: ").strip()

    # Step 3: exchange for access token
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=pin,
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
    _save_tokens(tokens)

    print(f"\n✅ E*TRADE access tokens saved to {TOKEN_PATH}")
    return tokens


def get_oauth_session() -> OAuth1Session:
    """
    Return an OAuth1Session using saved access tokens.

    - Requires ETRADE_API_KEY / ETRADE_API_SECRET in etrade.env.
    - Requires etrade_tokens.json with oauth_token + oauth_token_secret.
    - If tokens are missing, caller should trigger start_pin_flow()
      (we do NOT auto-prompt inside the web app).
    """
    _require_keys()

    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError(
            "E*TRADE tokens missing. Run 'python -m services.etrade_auth_flow' "
            "from C:\\TradeAlerts to complete the PIN auth flow."
        )

    return OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=tokens["oauth_token"],
        resource_owner_secret=tokens["oauth_token_secret"],
    )


# ----- CLI convenience -----
if __name__ == "__main__":
    # Allow: python -m services.etrade_auth_flow
    start_pin_flow()
