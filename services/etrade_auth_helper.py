from os import getenv
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

# load your .env, no filename needed
load_dotenv()

# pull in all four credentials
CONSUMER_KEY       = getenv("ETRADE_API_KEY")       or getenv("ETRADE_CONSUMER_KEY")
CONSUMER_SECRET    = getenv("ETRADE_API_SECRET")    or getenv("ETRADE_CONSUMER_SECRET")
OAUTH_TOKEN        = getenv("OAUTH_TOKEN")
OAUTH_TOKEN_SECRET = getenv("OAUTH_TOKEN_SECRET")

# also pull the environment flag
ETRADE_ENV         = getenv("ETRADE_ENV", "sandbox")  # production or sandbox

def make_etrade_session():
    """Return a ready-to-go OAuth1Session for E*TRADE."""
    if not all([CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET]):
        raise RuntimeError("E*TRADE credentials not set in environment")
    return OAuth1Session(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=OAUTH_TOKEN,
        resource_owner_secret=OAUTH_TOKEN_SECRET
    )
