import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trv_meta_counts_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_META_COUNTS_FROM_ARRAYS_V1"
if MARK in txt:
    print("Already patched (marker present).")
    raise SystemExit(0)

# Find api_trade_review function
m = re.search(r"(?ms)^def\s+api_trade_review\s*\(.*?\):\s*\n", txt)
if not m:
    # Sometimes it is named differently; try route handler name
    m = re.search(r"(?ms)^def\s+api_trade_review_.*?\(.*?\):\s*\n", txt)
if not m:
    raise SystemExit("ERROR: Could not find def api_trade_review... in dashboard.py")

start = m.start()

# Find the end of the function by next top-level def
m_end = re.search(r"(?ms)^\S", txt[m.end():])  # first non-indented line after def header scan is too naive
# We'll instead slice from def header to next top-level 'def ' or '@app.route' that starts at column 0
m_next = re.search(r"(?ms)^(def\s+|@app\.route)", txt[m.end():])
end = (m.end() + m_next.start()) if m_next else len(txt)

func = txt[start:end]

# Insert override just before the FIRST "return jsonify" inside this function
m_ret = re.search(r"(?m)^\s*return\s+jsonify\s*\(", func)
if not m_ret:
    raise SystemExit("ERROR: Could not find 'return jsonify(' inside api_trade_review handler.")

inject = """
    # --- {MARK} ---
    try:
        # Force meta counts to reflect the arrays we actually return (trade-specific truth)
        _out_locals = locals()
        _buy_arr = _out_locals.get("buy_triggers") or _out_locals.get("buy_rows") or _out_locals.get("buy_list") or []
        _sell_arr = _out_locals.get("sell_triggers") or _out_locals.get("sell_rows") or _out_locals.get("sell_list") or []
        if "meta" in _out_locals and isinstance(_out_locals["meta"], dict):
            _out_locals["meta"]["buy_ct"] = len(_buy_arr)
            _out_locals["meta"]["sell_ct"] = len(_sell_arr)
    except Exception:
        pass
    # --- /{MARK} ---
""".replace("{MARK}", MARK).rstrip() + "\n\n"

func2 = func[:m_ret.start()] + inject + func[m_ret.start():]

txt2 = txt[:start] + func2 + txt[end:]
P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
