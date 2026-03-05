import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\services\broker.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trade_time_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

# 1) Ensure we have a helper that computes ET ISO from ts_utc
if "MM_BROKER_TRADE_TIME_V1_START" not in txt:
    # Insert helper near top (after imports) in a safe way.
    ins = r"""
# --- MM_BROKER_TRADE_TIME_V1_START ---
def _mm_trade_time_et_iso(ts_utc: int | None) -> str:
    # Return ISO string in America/New_York (e.g., 2026-03-05 10:44:06-05:00)
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo as _ZI
        _et = _ZI("America/New_York")
    except Exception:
        _et = _dt.timezone(_dt.timedelta(hours=-5))
    try:
        if ts_utc is None:
            ts_utc = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
        d = _dt.datetime.fromtimestamp(int(ts_utc), _dt.timezone.utc).astimezone(_et)
        return d.isoformat(sep=" ", timespec="seconds")
    except Exception:
        return _dt.datetime.now().isoformat(sep=" ", timespec="seconds")
# --- MM_BROKER_TRADE_TIME_V1_END ---
""".lstrip("\n")

    # Insert after last import block at file top
    m = re.search(r'(?ms)\A((?:\s*#.*\n)*)\s*(import[^\n]*\n(?:from[^\n]*\n|import[^\n]*\n)*)', txt)
    if m:
        # Put helper right after the import cluster
        end = m.end()
        txt = txt[:end] + "\n" + ins + txt[end:]
    else:
        # Fallback: just prepend
        txt = ins + "\n" + txt

# 2) Patch the INSERT to include trade_time
# We expect something like:
#   INSERT INTO trades (ts_et, ts_utc, symbol, action, qty, price)
# and a corresponding execute(...) param tuple/list.
sql_pat = re.compile(r"INSERT\s+INTO\s+trades\s*\(\s*ts_et\s*,\s*ts_utc\s*,\s*symbol\s*,\s*action\s*,\s*qty\s*,\s*price\s*\)", re.IGNORECASE)
if not sql_pat.search(txt):
    raise SystemExit("ERROR: Could not find broker.py INSERT INTO trades(ts_et, ts_utc, symbol, action, qty, price) (file drift)")

txt2 = sql_pat.sub("INSERT INTO trades (trade_time, ts_et, ts_utc, symbol, action, qty, price)", txt)

# 3) Patch the execute param list to add trade_time as first value.
# We’ll target the most common pattern: execute(SQL, (ts_et, ts_utc, symbol, action, qty, price))
# and convert to: execute(SQL, (_mm_trade_time_et_iso(ts_utc), ts_et, ts_utc, ...))
param_pat = re.compile(
    r"(\.execute\(\s*[^,]+,\s*\()\s*(ts_et)\s*,\s*(ts_utc)\s*,\s*(symbol)\s*,\s*(action)\s*,\s*(qty)\s*,\s*(price)\s*(\)\s*\))",
    re.IGNORECASE
)

if not param_pat.search(txt2):
    # Try tuple wrapped: (ts_et, ts_utc, ...)
    param_pat = re.compile(
        r"(\.execute\(\s*[^,]+,\s*\(\s*)\s*(ts_et)\s*,\s*(ts_utc)\s*,\s*(symbol)\s*,\s*(action)\s*,\s*(qty)\s*,\s*(price)\s*(\s*\)\s*\)\s*\))",
        re.IGNORECASE
    )

if not param_pat.search(txt2):
    raise SystemExit("ERROR: Could not patch broker.py execute(...) params for trades insert (file drift). Paste the trades insert function and I’ll pin it exactly.")

txt3 = param_pat.sub(r"\1_mm_trade_time_et_iso(\3), \2, \3, \4, \5, \6, \7\8", txt2)

P.write_text(txt3, encoding="utf-8")
print("PATCHED ->", P)
