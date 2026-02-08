import re
from pathlib import Path
from datetime import datetime

p = Path(r"C:\TradeAlerts\services\etrade_service.py")
src = p.read_text(encoding="utf-8", errors="ignore")

bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
bak.write_text(src, encoding="utf-8")
print("Backup ->", bak)

# Grab the whole function block for list_trade_transactions(...)
m = re.search(r'(?ms)^def\s+list_trade_transactions\s*\(.*?\)\s*:\s*\n(.*?)(?=^\S|\Z)', src)
if not m:
    raise SystemExit("ERROR: could not find def list_trade_transactions(...) block")

old_block = m.group(0)

# Replacement: keep signature flexible and only change this function.
# - prefer numeric _primary_account_id when available
# - retry with the other id if 500
# - on persistent 500, return {} (do not raise)
new_block = r'''def list_trade_transactions(days=90, account_id=None, account_key=None, count=200):
    """
    Fetch TRADE transactions from E*TRADE.

    IMPORTANT:
      - Some E*TRADE endpoints tolerate accountIdKey; transactions often wants numeric accountId.
      - E*TRADE can return HTTP 500 (code 100) transiently or when given the "wrong" id form.
      - This function should not crash the app on 500; it will retry once and then return {}.
    """
    import datetime as _dt

    # Decide which account identifier to use.
    # Prefer numeric id if we have it.
    aid_numeric = None
    try:
        aid_numeric = str(globals().get("_primary_account_id") or "").strip()
        if not aid_numeric.isdigit():
            aid_numeric = None
    except Exception:
        aid_numeric = None

    aid_key = None
    try:
        aid_key = str(globals().get("_primary_account_key") or "").strip()
        if not aid_key:
            aid_key = None
    except Exception:
        aid_key = None

    # Caller overrides
    if account_id:
        s = str(account_id).strip()
        if s.isdigit():
            aid_numeric = s
        else:
            # allow caller to pass key here; we'll treat as key
            aid_key = s
    if account_key:
        s = str(account_key).strip()
        if s:
            aid_key = s

    # Primary choice: numeric if present, else key
    first = aid_numeric or aid_key
    second = None
    if first == aid_numeric and aid_key:
        second = aid_key
    elif first == aid_key and aid_numeric:
        second = aid_numeric

    if not first:
        raise RuntimeError("No E*TRADE account id/key available for transactions call")

    # Date range
    today = _dt.date.today()
    start = today - _dt.timedelta(days=int(days or 0))
    end = today  # never ask for future dates

    params = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "category": "TRADE",
        "count": int(count or 200),
    }

    def _do(aid_value):
        url = f"{API_BASE}/accounts/{aid_value}/transactions.json"
        r = _oauth_get(url, params=params)
        if r is None:
            return None, None
        return r, url

    # Attempt 1
    r, url = _do(first)
    if r is None:
        return {}

    # If 500, retry with alternate id form (if available)
    if r.status_code >= 500 and second:
        try:
            r2, url2 = _do(second)
            if r2 is not None:
                r = r2
                url = url2
        except Exception:
            pass

    # Still 500? fail soft
    if r.status_code >= 500:
        try:
            _lg.warning("E*TRADE transactions HTTP %s for %s (returning empty)", r.status_code, url)
        except Exception:
            pass
        return {}

    # Non-500 errors: keep existing behavior (raise)
    r.raise_for_status()
    try:
        return r.json() or {}
    except Exception:
        return {}
'''

src2 = src.replace(old_block, new_block)
if src2 == src:
    raise SystemExit("ERROR: replacement did not change file (unexpected)")

p.write_text(src2, encoding="utf-8")
print("OK patched list_trade_transactions() to prefer numeric id and fail-soft on 500")
