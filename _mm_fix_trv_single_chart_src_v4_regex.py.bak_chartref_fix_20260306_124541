import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_fix_chart_src_v4_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

new_block = '''<img class="tr-chart trade-chart-img"
         src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else '') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"
         alt="Trade chart {{ trade.symbol }}{% if name %} ? {{ name }}{% endif %}">'''

pat = re.compile(
    r'<img\s+class="tr-chart trade-chart-img"[\s\S]*?alt="Trade chart.*?">\s*',
    re.I
)

m = pat.search(txt)
if not m:
    raise SystemExit("Could not find chart img block in trade_review_single.html")

txt = txt[:m.start()] + new_block + "\n" + txt[m.end():]
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_SINGLE_CHART_SRC_V4_REGEX")
