import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\services\etrade_service.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_place_equity_order_dict_fix_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# Locate place_equity_order() body
m = re.search(r'(?ms)^def\s+place_equity_order\([^\n]*\n.*?(?=^def\s|\Z)', txt)
if not m:
    raise SystemExit("ERROR: could not find def place_equity_order(...) block")

block = m.group(0)

# Anchor on the exact problematic status_code section inside the function
pat = re.compile(
    r'(?ms)^\s*if 200 <= resp\.status_code < 300:\s*\n'
    r'\s*return resp\.json\(\)\s*\n\s*\n'
    r'\s*if resp\.status_code == 500:.*?\n'
    r'\s*resp\.raise_for_status\(\)\s*$'
)

mm = pat.search(block)
if not mm:
    raise SystemExit("ERROR: could not find the resp.status_code decision block to patch (file drift)")

replacement = r'''        # --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V1_START ---
        # NOTE: some internal wrappers return already-decoded JSON (dict) instead of requests.Response.
        # If we treat that dict like a Response, we crash (dict has no .status_code), and Sell Guard retries
        # with the same clientOrderId, causing E*TRADE code 1028 duplicate spam.
        if isinstance(resp, dict):
            # If this dict is actually an E*TRADE Error payload, raise with a code-bearing message
            try:
                err = (resp.get("Error") or {}) if isinstance(resp, dict) else {}
                code = err.get("code") if isinstance(err, dict) else None
                msg  = err.get("message") if isinstance(err, dict) else None
                if code is not None:
                    # Preserve the "code': 1028" pattern Sell Guard already keys off of
                    raise RuntimeError(f"etrade POST {path} -> 400: {{'Error': {{'code': {code}, 'message': {msg!r}}}}} | payload={body!r}")
            except Exception:
                # If the error parse above raised, let it bubble
                raise
            # Otherwise this is a success-ish JSON payload already
            return resp

        if 200 <= resp.status_code < 300:
            try:
                return resp.json() or {}
            except Exception:
                return {"raw_text": getattr(resp, "text", "")}

        if resp.status_code == 500:
            try:
                err_json = resp.json() or {}
            except Exception:  # noqa: BLE001
                err_json = {}
            err = (err_json or {}).get("Error") or {}
            code = str(err.get("code")) if err else None
            if code == "100":
                LOG.warning(
                    "place_equity_order transient venue error for %s (outer=%s): %s",
                    symbol or "?",
                    outer,
                    err,
                )
                # Retry with the same body; if it keeps failing we'll
                # eventually bubble the error up to the caller.
                continue

        # Non-OK / non-transient response
        resp.raise_for_status()
        # --- MM_PLACE_EQUITY_ORDER_DICT_FIX_V1_END ---'''

new_block = block[:mm.start()] + re.sub(pat, replacement, block[mm.start():mm.end()], count=1) + block[mm.end():]

new_txt = txt[:m.start()] + new_block + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print(f"PATCHED -> {P}")
