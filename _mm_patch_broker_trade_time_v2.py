import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\services\broker.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trade_time_v2_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

OLD_SQL = "INSERT INTO trades (ts_et, ts_utc, symbol, action, qty, price)"
NEW_SQL = "INSERT INTO trades (trade_time, ts_et, ts_utc, symbol, action, qty, price)"

if OLD_SQL not in txt and NEW_SQL in txt:
    print("SQL already updated (NEW_SQL present). Will still try to patch execute params.")
elif OLD_SQL in txt:
    txt = txt.replace(OLD_SQL, NEW_SQL)
else:
    raise SystemExit("ERROR: Could not find the exact trades INSERT SQL string (file drift).")

# Patch execute(...) param tuples that match the 6-value insert
# We target: execute(<sql>, (<a>, <b>, <c>, <d>, <e>, <f>))
# and convert to: execute(<sql>, (<b>, <a>, <b>, <c>, <d>, <e>, <f>))
#
# IMPORTANT: we only patch the execute call if the nearby SQL (same line or preceding few lines)
# contains "INSERT INTO trades" and includes "ts_et, ts_utc".
lines = txt.splitlines(True)

out = []
patched = 0
for i, line in enumerate(lines):
    out.append(line)

    # Look back a few lines for the SQL string / assignment containing INSERT INTO trades
    lookback = "".join(lines[max(0, i-6):i+1])
    if ("INSERT INTO trades" not in lookback) or ("ts_et" not in lookback) or ("ts_utc" not in lookback):
        continue

    # Patch only on lines that actually call execute(...)
    if ".execute(" not in line:
        continue

    # Try to patch tuple params in THIS line (common case)
    m = re.search(
        r"(?P<prefix>\.execute\(\s*[^,]+,\s*\(\s*)"
        r"(?P<a>[^,\n\)]+)\s*,\s*(?P<b>[^,\n\)]+)\s*,\s*(?P<c>[^,\n\)]+)\s*,\s*"
        r"(?P<d>[^,\n\)]+)\s*,\s*(?P<e>[^,\n\)]+)\s*,\s*(?P<f>[^,\n\)]+)"
        r"(?P<suffix>\s*\)\s*\)\s*\))",
        line
    )
    if not m:
        continue

    # Avoid double-patching if trade_time already in the tuple (7 args)
    if m.group("a").strip() == m.group("b").strip() and "trade_time" in lookback:
        continue

    a = m.group("a").strip()
    b = m.group("b").strip()
    c = m.group("c").strip()
    d = m.group("d").strip()
    e = m.group("e").strip()
    f = m.group("f").strip()

    new_line = (
        line[:m.start()] +
        m.group("prefix") +
        f"{b}, {a}, {b}, {c}, {d}, {e}, {f}" +
        m.group("suffix") +
        line[m.end():]
    )

    out[-1] = new_line
    patched += 1

new_txt = "".join(out)
P.write_text(new_txt, encoding="utf-8")
print("Execute param tuples patched ->", patched)
print("PATCHED ->", P)
