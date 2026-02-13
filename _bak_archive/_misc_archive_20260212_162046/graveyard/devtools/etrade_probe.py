# etrade_probe.py
import json, os
from datetime import datetime
from services.etrade_service import _eget, _primary_account_id

def walk(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):              # show first 5 items only
            yield from walk(v, f"{prefix}[{i}]")
        if len(obj) > 5:
            yield f"{prefix}[...]", f"{len(obj)-5} more items"
    else:
        yield prefix, obj

def dump(endpoint, params=None, name=None):
    r = _eget(endpoint, params or {})
    j = r.json()
    title = name or endpoint
    print(f"\n=== {title} ({r.status_code}) ===")
    print(json.dumps(j, indent=2)[:2000])            # print first ~2KB of pretty JSON
    print("\n--- Fields (dot paths) ---")
    for path, val in walk(j):
        t = type(val).__name__
        sample = val if isinstance(val, (int, float, str, bool)) else ""
        if isinstance(sample, str) and len(sample) > 80:
            sample = sample[:77] + "..."
        print(f"{path}  [{t}]  {sample}")
    # also save full JSON to disk
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"logs/etrade_dump_{(name or endpoint).strip('/').replace('/','_')}_{ts}.json"
    os.makedirs("logs", exist_ok=True)
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(j, f, indent=2)
    print(f"\n(saved full JSON to {fn})")

if __name__ == "__main__":
    aid = _primary_account_id()
    dump("/v1/accounts/list.json",                     name="accounts.list")
    dump(f"/v1/accounts/{aid}/balance.json",  {"instType":"BROKERAGE"}, name="accounts.balance")
    dump(f"/v1/accounts/{aid}/portfolio.json",{"instType":"BROKERAGE"}, name="accounts.portfolio")
    # optional: peek at a quote shape too
    dump("/v1/market/quote/AAPL.json",                 name="market.quote.AAPL")
