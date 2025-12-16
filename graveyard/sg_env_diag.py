# sg_env_diag.py
# Quick checks for env, .env, and API connectivity used by sell_guard.py

import importlib
import json
import os
import re
import sys
from datetime import datetime

print("=== sg_env_diag starting ===", datetime.utcnow().isoformat() + "Z")
print("cwd:", os.getcwd())
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
print("sys.path[0]:", sys.path[0] if sys.path else None)

# 1) .env detection & loading
try:
    from dotenv import find_dotenv, load_dotenv

    env_path = find_dotenv(usecwd=True)
    print("find_dotenv(usecwd=True) ->", env_path or "<none>")
    if env_path:
        loaded = load_dotenv(env_path, override=False)
        print("load_dotenv ->", loaded)
    else:
        # Also try parent dirs for Windows PS launches
        loaded = False
    # Secondary: if a TRADEALERTS_DIR is set, try loading there too
    ta_dir = os.environ.get("TRADEALERTS_DIR") or r"C:\TradeAlerts"
    try_env2 = os.path.join(ta_dir, ".env")
    if os.path.exists(try_env2):
        loaded2 = load_dotenv(try_env2, override=False)
        print(f"load_dotenv({try_env2}) ->", loaded2)
except Exception as e:
    print("python-dotenv not available or failed:", repr(e))

# 2) Check the keys we expect for the broker API (mask values)
# E*TRADE-style names (adapt if your service uses different ones)
expected = [
    "ETRADE_CONSUMER_KEY",
    "ETRADE_CONSUMER_SECRET",
    "ETRADE_OAUTH_TOKEN",
    "ETRADE_OAUTH_SECRET",
    "ETRADE_ACCOUNT_ID_KEY",
    "ETRADE_ENV",  # e.g., "production"
    "ETRADE_BASE_URL",  # optional override
    "ETRADE_SANDBOX",  # optional flag
]
present = {}
for k in expected:
    v = os.environ.get(k)
    if not v:
        present[k] = None
    else:
        # mask value but keep last 4 chars for debugging
        mask = v if len(v) <= 4 else ("*" * (len(v) - 4) + v[-4:])
        present[k] = mask
print("ENV keys (masked):", json.dumps(present, indent=2))

missing = [
    k
    for k, v in present.items()
    if v is None and k not in ("ETRADE_BASE_URL", "ETRADE_SANDBOX")
]
if missing:
    print("!! MISSING (required) env keys:", missing)
else:
    print("All required keys appear present (masked above).")

# 3) Import service the same way sell_guard does
et = None
try:
    try:
        et = importlib.import_module("services.etrade_service")
        print("Imported services.etrade_service")
    except Exception:
        et = importlib.import_module("etrade_service")
        print("Imported local etrade_service")
except Exception as e:
    print("!! Could not import etrade_service:", repr(e))
    et = None


# Helper: run a function if it exists
def try_call(name, *args, **kwargs):
    if et is None:
        print(f"skip {name}: no service module")
        return None
    fn = getattr(et, name, None)
    if not callable(fn):
        print(f"no function {name} on etrade_service")
        return None
    try:
        out = fn(*args, **kwargs)
        print(f"{name} OK")
        try:
            js = json.dumps(out, indent=2)[:800]
            print(f"{name} -> (truncated)\n{js}")
        except Exception:
            print(f"{name} returned non-JSON serializable type: {type(out)}")
        return out
    except Exception as e:
        s = str(e)
        # show HTTP-ish status if present
        status = re.search(r"->\s*(\d{3})", s)
        code = re.search(r"'code':\s*(\d+)", s) or re.search(r'"code":\s*(\d+)', s)
        print(f"{name} ERROR:", repr(e))
        if status:
            print("  parsed http status:", status.group(1))
        if code:
            print("  parsed venue code:", code.group(1))
        return None


# 4) Basic "who am I" & account tests
aid = None
if et:
    aid = try_call("account_id_key")
    # positions (read)
    _ = try_call("get_positions", aid if aid else None)
    # quotes (read) - cheap single symbol
    _ = try_call("get_quote", "SPY")

# 5) Preview a SELL (harmless) if preview API is exposed.
# We'll try a preview function name first; if not present, try place_order with preview=True.
if et and aid:
    did_preview = False
    for name in (
        "preview_order",
        "preview_limit_sell",
        "preview_sell",
        "order_preview",
    ):
        if getattr(et, name, None):
            _ = try_call(name, aid, symbol="MSFT", qty=1, price=9999.0)
            did_preview = True
            break
    if not did_preview and getattr(et, "place_order", None):
        print("Trying place_order(..., preview=True) so it does NOT execute")
        _ = try_call(
            "place_order",
            aid,
            symbol="MSFT",
            side="SELL",
            qty=1,
            price=9999.0,
            order_type="LIMIT",
            preview=True,
        )

print("=== sg_env_diag done ===")
