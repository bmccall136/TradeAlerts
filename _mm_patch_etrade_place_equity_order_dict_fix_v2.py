import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\services\etrade_service.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_place_equity_order_dict_fix_v2_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

m = re.search(r'(?ms)^def\s+place_equity_order\([^\n]*\n.*?(?=^def\s|\Z)', txt)
if not m:
    raise SystemExit("ERROR: could not find def place_equity_order(...) block")

block = m.group(0)

if "MM_PLACE_EQUITY_ORDER_DICT_FIX_V2_START" in block:
    print("Already patched (V2 marker found). No changes.")
    raise SystemExit(0)

# Find the line where we get the response back from the POST helper inside place_equity_order
# This should match either resp = _epost(...) or resp = _post(...)
post_line = re.search(r'(?m)^(?P<indent>\s*)resp\s*=\s*_(?:e)?post\([^\n]*\)\s*$', block)
if not post_line:
    # fallback: sometimes wrapped differently; match a resp assignment calling _epost/_post across a line
    post_line = re.search(r'(?m)^(?P<indent>\s*)resp\s*=\s*_(?:e)?post\([^\n]*$', block)
if not post_line:
    raise SystemExit("ERROR: could not find resp = _epost/_post(...) inside place_equity_order (file drift)")

indent = post_line.group("indent")

inject = (
f"""{indent}# --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V2_START ---
{indent}# Some internal wrappers may return already-decoded JSON (dict) instead of requests.Response.
{indent}# If we treat dict like a Response, we crash (no .status_code) and Sell Guard retries, causing E*TRADE 1028 duplicates.
{indent}if isinstance(resp, dict):
{indent}    err = (resp.get("Error") or {}) if isinstance(resp, dict) else {{}}
{indent}    code = err.get("code") if isinstance(err, dict) else None
{indent}    msg  = err.get("message") if isinstance(err, dict) else None
{indent}    if code is not None:
{indent}        # Preserve the "code': 1028" pattern Sell Guard keys off of
{indent}        raise RuntimeError(f"etrade POST {{path}} -> 400: {{'Error': {{'code': {{code}}, 'message': {{msg!r}}}}}} | payload={{body!r}}")
{indent}    return resp
{indent}# --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V2_END ---
"""
)

# Insert immediately after the resp=... line (keep structure intact)
ins_at = post_line.end()
block2 = block[:ins_at] + "\n" + inject + block[ins_at:]

new_txt = txt[:m.start()] + block2 + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print(f"PATCHED -> {P}")
