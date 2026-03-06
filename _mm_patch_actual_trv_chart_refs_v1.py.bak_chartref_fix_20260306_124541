import pathlib, shutil, datetime, re

ROOT = pathlib.Path(r"C:\TradeAlerts")
files = list(ROOT.rglob("*.html")) + list(ROOT.rglob("*.py"))
hits = []

for p in files:
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if '/trade_review/chart?symbol=' in txt:
        hits.append((p, txt))

print("HITS:")
for p, _ in hits:
    print(" -", p)

if not hits:
    raise SystemExit("No files contain /trade_review/chart?symbol=")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

for p, txt in hits:
    bak = p.with_name(p.name + f".bak_chartref_fix_{ts}")
    shutil.copy2(p, bak)

    txt2 = txt

    txt2 = re.sub(
        r'src="/trade_review/chart\?symbol=\{\{ symbol if symbol is defined else \(trade\.symbol if trade is defined and trade else \'\'\) \}\}&v=\{\{ \(trade\.ts_utc if trade is defined and trade and trade\.ts_utc else \(trade_id if trade_id else 0\)\) \}\}"',
        r'src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else \'\') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"',
        txt2
    )

    txt2 = txt2.replace(
        'src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else \'\') }}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"',
        'src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else \'\') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"'
    )

    if txt2 != txt:
        p.write_text(txt2, encoding="utf-8", newline="\n")
        print("PATCHED ->", p)
        patched += 1
    else:
        print("UNCHANGED ->", p)

print("PATCH_COUNT =", patched)
if patched == 0:
    raise SystemExit("Found files, but none matched the exact old src string.")
