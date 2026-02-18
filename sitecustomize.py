# MM_SITECUSTOMIZE_LOAD_DOTENV_V2
# Auto-load C:\TradeAlerts\.env into os.environ for all Python runs
# (works with venv + mm_tradealerts.pth).

import os
from pathlib import Path

def _mm_load_dotenv(env_path: Path) -> None:
    try:
        txt = env_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    for ln in txt.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if k not in os.environ:
            os.environ[k] = v

try:
    _mm_load_dotenv(Path(__file__).resolve().parent / ".env")

    # Token aliases used across the codebase
    if os.getenv("OAUTH_TOKEN") and not os.getenv("ETRADE_OAUTH_TOKEN"):
        os.environ["ETRADE_OAUTH_TOKEN"] = os.getenv("OAUTH_TOKEN", "")
    if os.getenv("OAUTH_TOKEN_SECRET") and not os.getenv("ETRADE_OAUTH_TOKEN_SECRET"):
        os.environ["ETRADE_OAUTH_TOKEN_SECRET"] = os.getenv("OAUTH_TOKEN_SECRET", "")
    if os.getenv("OAUTH_TOKEN") and not os.getenv("ETRADE_ACCESS_TOKEN"):
        os.environ["ETRADE_ACCESS_TOKEN"] = os.getenv("OAUTH_TOKEN", "")
    if os.getenv("OAUTH_TOKEN_SECRET") and not os.getenv("ETRADE_ACCESS_SECRET"):
        os.environ["ETRADE_ACCESS_SECRET"] = os.getenv("OAUTH_TOKEN_SECRET", "")
except Exception:
    # never block interpreter startup
    pass
