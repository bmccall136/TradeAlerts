import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trv_meta_counts_v2_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_META_COUNTS_FROM_RETURN_PAYLOAD_V2"
if MARK in txt:
    print("Already patched (marker present).")
    raise SystemExit(0)

# Locate api_trade_review function block
m = re.search(r"(?ms)^def\s+api_trade_review\b.*?:\n", txt)
if not m:
    # fallback: any function that starts with api_trade_review
    m = re.search(r"(?ms)^def\s+api_trade_review\w*\b.*?:\n", txt)
if not m:
    raise SystemExit("ERROR: Could not find api_trade_review function in dashboard.py")

start = m.start()
m_next = re.search(r"(?ms)^(def\s+|@app\.route)", txt[m.end():])
end = (m.end() + m_next.start()) if m_next else len(txt)
func = txt[start:end]

# Find the return jsonify({...}) (use the LAST one in case there are early returns)
rets = list(re.finditer(r"(?m)^\s*return\s+jsonify\s*\(\s*\{", func))
if not rets:
    raise SystemExit("ERROR: Could not find 'return jsonify({ ...' inside api_trade_review.")
ret = rets[-1]

# From the return dict area, extract variable names for buy_triggers/sell_triggers/meta
# We'll scan a window forward from the return for the dict literal text.
window = func[ret.start(): ret.start()+5000]  # plenty for payload
buy_m  = re.search(r"""['"]buy_triggers['"]\s*:\s*([A-Za-z_][A-Za-z0-9_]*)""", window)
sell_m = re.search(r"""['"]sell_triggers['"]\s*:\s*([A-Za-z_][A-Za-z0-9_]*)""", window)
meta_m = re.search(r"""['"]meta['"]\s*:\s*([A-Za-z_][A-Za-z0-9_]*)""", window)

if not (buy_m and sell_m and meta_m):
    raise SystemExit(
        "ERROR: Could not parse return payload var names. "
        f"buy={bool(buy_m)} sell={bool(sell_m)} meta={bool(meta_m)}"
    )

buy_var  = buy_m.group(1)
sell_var = sell_m.group(1)
meta_var = meta_m.group(1)

inject = f"""
    # --- {MARK} ---
    try:
        _b = {buy_var} if {buy_var} is not None else []
        _s = {sell_var} if {sell_var} is not None else []
        if isinstance({meta_var}, dict):
            {meta_var}["buy_ct"] = len(_b)
            {meta_var}["sell_ct"] = len(_s)
    except Exception:
        pass
    # --- /{MARK} ---
""".rstrip() + "\n\n"

# Insert just BEFORE the return line we found (at column indent level)
func2 = func[:ret.start()] + inject + func[ret.start():]

txt2 = txt[:start] + func2 + txt[end:]
P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
print("Parsed payload vars:", "buy_triggers=>"+buy_var, "sell_triggers=>"+sell_var, "meta=>"+meta_var)
