# env_alias_shim.py
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith("'") and v.endswith("'")) or (
        v.startswith('"') and v.endswith('"')
    ):
        return v[1:-1]
    return v


def ensure_env_aliases():
    alias_map = {
        "ETRADE_CONSUMER_KEY": ["ETRADE_API_KEY", "CONSUMER_KEY"],
        "ETRADE_CONSUMER_SECRET": ["ETRADE_API_SECRET", "CONSUMER_SECRET"],
        "ETRADE_OAUTH_TOKEN": ["OAUTH_TOKEN"],
        "ETRADE_OAUTH_SECRET": ["OAUTH_TOKEN_SECRET"],
        "ETRADE_ACCOUNT_ID_KEY": ["ACCOUNT_ID_KEY"],  # optional, if you have it
    }
    for target, sources in alias_map.items():
        if not os.environ.get(target):
            for src in sources:
                val = os.environ.get(src)
                if val:
                    os.environ[target] = _strip_quotes(val)
                    break
