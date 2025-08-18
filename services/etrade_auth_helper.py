# services/etrade_auth_helper.py
import os, time
from pathlib import Path
from dotenv import load_dotenv, set_key
from requests_oauthlib import OAuth1Session

# Files we watch for changes
ENV_FILES = [".env", "etrade.env"]
_last_mtime = 0

# Load once at import (ok if files exist yet)
for f in ENV_FILES:
    if os.path.exists(f):
        load_dotenv(f, override=True)

def _refresh_env():
    """Reload env vars if .env / etrade.env changed on disk."""
    global _last_mtime
    try:
        m = sum(os.path.getmtime(f) for f in ENV_FILES if os.path.exists(f))
    except Exception:
        m = 0
    if m != _last_mtime:
        for f in ENV_FILES:
            if os.path.exists(f):
                load_dotenv(f, override=True)
        _last_mtime = m

def _get(*keys):
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None

def get_etrade_session():
    """
    Build an OAuth1Session using current env vars.
    Hot-reloads .env/etrade.env if they changed.
    """
    _refresh_env()
    ck  = _get("ETRADE_CONSUMER_KEY", "ETRADE_API_KEY")
    cs  = _get("ETRADE_CONSUMER_SECRET", "ETRADE_API_SECRET")
    tok = _get("ETRADE_OAUTH_TOKEN", "OAUTH_TOKEN")
    sec = _get("ETRADE_OAUTH_TOKEN_SECRET", "OAUTH_TOKEN_SECRET")
    if not all([ck, cs, tok, sec]):
        raise RuntimeError("Missing E*TRADE env vars (key/secret/token/secret).")
    return OAuth1Session(
        client_key=ck, client_secret=cs,
        resource_owner_key=tok, resource_owner_secret=sec
    )

# Back-compat alias if other code imports this name
make_etrade_session = get_etrade_session

from dotenv import load_dotenv, set_key
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

def save_tokens(token, secret):
    set_key(ENV_PATH, "OAUTH_TOKEN", token)
    set_key(ENV_PATH, "OAUTH_TOKEN_SECRET", secret)
    set_key(ENV_PATH, "ETRADE_OAUTH_TOKEN", token)
    set_key(ENV_PATH, "ETRADE_OAUTH_TOKEN_SECRET", secret)
    load_dotenv(dotenv_path=ENV_PATH, override=True)


def clear_need_auth_flag(flag_path: str = "need_oauth.flag"):
    try:
        Path(flag_path).unlink(missing_ok=True)
    except Exception:
        pass

def get_api_host() -> str:
    """
    Helper: choose sandbox vs live base host from ETRADE_ENV.
    """
    _refresh_env()
    env = (os.getenv("ETRADE_ENV") or "sandbox").lower()
    return "https://apisb.etrade.com" if env.startswith("sand") else "https://api.etrade.com"
