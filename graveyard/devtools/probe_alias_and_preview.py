# probe_alias_and_preview.py
import json, inspect, os, sys, traceback
from env_alias_shim import ensure_env_aliases
ensure_env_aliases()

# Import the trading service like sell_guard
try:
    from services import etrade_service as et
except Exception:
    import etrade_service as et

# Ensure ACCOUNT_ID_KEY is visible to any code that reads it from env
try:
    aid = et.account_id_key()
except Exception as e:
    print("account_id_key() failed:", repr(e))
    sys.exit(1)
if not os.getenv("ETRADE_ACCOUNT_ID_KEY"):
    os.environ["ETRADE_ACCOUNT_ID_KEY"] = aid

print("Mapped keys present?:", {
    k: bool(os.getenv(k)) for k in
    ["ETRADE_CONSUMER_KEY","ETRADE_CONSUMER_SECRET","ETRADE_OAUTH_TOKEN","ETRADE_OAUTH_SECRET","ETRADE_ACCOUNT_ID_KEY"]
})
print("account_id_key:", aid)

symbol = "SPY"   # liquid, safe for preview
qty_val = 1

# Candidate functions in order of preference
candidates = []
for name in ("preview_equity_order","preview_order","place_order"):
    fn = getattr(et, name, None)
    if callable(fn):
        candidates.append((name, fn))

if not candidates:
    print("No preview/place function found on etrade_service.")
    print("Available names:", [n for n in dir(et) if "order" in n.lower()])
    sys.exit(1)

# Value options to try for each semantic field
qty_keys = ["quantity", "qty", "Quantity"]
price_type_keys = ["price_type", "priceType", "orderType", "priceTypeCode"]
action_keys = ["action", "side", "orderAction", "orderSide"]
price_keys = ["price", "limitPrice"]  # for MARKET we pass None if allowed
preview_keys = ["preview", "isPreview"]

attempts = []

for fn_name, fn in candidates:
    params = list(inspect.signature(fn).parameters.keys())
    attempts.append((fn_name, fn, params))

def try_call(fn_name, fn):
    params = list(inspect.signature(fn).parameters.keys())
    print(f"Trying {fn_name}{tuple(params)}")

    # Build a few kwargs variants based on the parameters we see
    base_variants = []

    # Common baseline: account id + symbol + qty + MARKET + SELL (preview if supported)
    def make_kwargs(qty_key, pt_key, act_key, price_key=None, preview_key=None):
        kw = {}
        # account id key variants
        for k in ("account_id_key","accountIdKey","accountKey","account_id","accountId"):
            if k in params: kw[k] = aid; break
        if "symbol" in params: kw["symbol"] = symbol
        if qty_key in params: kw[qty_key] = qty_val
        if pt_key in params:  kw[pt_key]  = "MARKET"
        if act_key in params: kw[act_key] = "SELL"
        if price_key and price_key in params:
            kw[price_key] = None
        if preview_key and preview_key in params:
            kw[preview_key] = True
        return kw

    # generate combos
    for qk in qty_keys:
        for ptk in price_type_keys:
            for ak in action_keys:
                # with/without explicit price, with/without preview flag
                base_variants.append(make_kwargs(qk, ptk, ak))
                base_variants.append(make_kwargs(qk, ptk, ak, price_key="price"))
                base_variants.append(make_kwargs(qk, ptk, ak, preview_key="preview"))
                base_variants.append(make_kwargs(qk, ptk, ak, price_key="price", preview_key="preview"))

    errors = []
    for i, kw in enumerate(base_variants, 1):
        # Only keep kwargs the function actually accepts
        filtered = {k:v for k,v in kw.items() if k in params}
        # Skip empty/no-op attempts
        if not filtered or "symbol" not in filtered or not any(k in filtered for k in qty_keys):
            continue
        try:
            res = fn(**filtered)
            print(f"SUCCESS with kwargs #{i}: {filtered}")
            print("PREVIEW OK")
            print(json.dumps(res, indent=2)[:1500], "...")
            return True
        except TypeError as te:
            # Signature mismatch: keep trying
            errors.append(("TypeError", str(te), filtered))
            continue
        except Exception as e:
            # Non-TypeError means we hit the endpoint with valid signature; show payload+error
            print(f"Endpoint responded (non-TypeError) with kwargs #{i}: {filtered}")
            print("ERROR:", repr(e))
            # If you see HTTP 4xx/5xx here, creds & signature are fine; it’s a business/API rule.
            return False

    # If we exhausted variants for this fn
    print(f"All variants failed for {fn_name}. Signature was: {params}")
    if errors:
        print("Sample TypeErrors (up to 3):")
        for row in errors[:3]:
            print("  ", row)
    return False

worked = False
for fn_name, fn, _ in attempts:
    ok = try_call(fn_name, fn)
    if ok:
        worked = True
        break

if not worked:
    print("\nNo combination succeeded. This usually means the function is named differently,")
    print("or requires extra params (e.g., orderTerm, marketSession). Here are the params we saw:")
    for fn_name, _, params in attempts:
        print(f"  {fn_name}: {params}")
