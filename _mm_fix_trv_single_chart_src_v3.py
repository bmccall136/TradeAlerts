import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_fix_chart_src_v3_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = '''src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else \'\') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"'''

new = '''src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else '') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"'''

if old not in txt:
    raise SystemExit("Target src line not found in trade_review_single.html")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_SINGLE_CHART_SRC_V3")
