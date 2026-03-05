import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\services\etrade_service.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_place_equity_order_dict_fix_v3_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

m = re.search(r'(?ms)^def\s+place_equity_order\([^\n]*\n.*?(?=^def\s|\Z)', txt)
if not m:
    raise SystemExit("ERROR: could not find def place_equity_order(...) block")

block = m.group(0)

if "MM_PLACE_EQUITY_ORDER_DICT_FIX_V3_START" in block:
    print("Already patched (V3 marker found). No changes.")
    raise SystemExit(0)

# Find resp assignment to POST helper inside place_equity_order
post_line = re.search(r'(?m)^(?P<indent>\s*)resp\s*=\s*_(?:e)?post\([^\n]*\)\s*$', block)
if not post_line:
    # fallback: resp assignment line might wrap; match the start of it
    post_line = re.search(r'(?m)^(?P<indent>\s*)resp\s*=\s*_(?:e)?post\([^\n]*$', block)

if not post_line:
    raise SystemExit("ERROR: could not find resp = _epost/_post(...) inside place_equity_order (file drift)")

indent = post_line.group("indent")

# Build injected code without using f-strings in THIS patcher (braces safe)
lines = [
    "# --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V3_START ---",
    "# Some internal wrappers may return already-decoded JSON (dict) instead of requests.Response.",
    "# If we treat dict like a Response, we crash (no .status_code) and Sell Guard retries, causing 1028 duplicates.",
    "if isinstance(resp, dict):",
    "    err = (resp.get('Error') or {}) if isinstance(resp, dict) else {}",
    "    code = err.get('code') if isinstance(err, dict) else None",
    "    msg  = err.get('message') if isinstance(err, dict) else None",
    "    if code is not None:",
    "        # Preserve the \"code': 1028\" pattern Sell Guard keys off of",
    "        raise RuntimeError(f\"etrade POST {path} -> 400: {{'Error': {{'code': {code}, 'message': {msg!r}}}}} | payload={body!r}\")",
    "    return resp",
    "# --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V3_END ---",
]
inject = "\n".join(indent + ln for ln in lines) + "\n"

# Insert immediately after resp=... line (keep try/except structure intact)
ins_at = post_line.end()
block2 = block[:ins_at] + "\n" + inject + block[ins_at:]

new_txt = txt[:m.start()] + block2 + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print(f"PATCHED -> {P}")
