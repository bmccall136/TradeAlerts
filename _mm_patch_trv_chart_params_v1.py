import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
if not P.exists():
    raise SystemExit(f"Template not found: {P}")

txt = P.read_text(encoding="utf-8", errors="replace")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_chart_params_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """<img class="tr-chart trade-chart-img"
         src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else \'\') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"
         alt="Trade chart {{ trade.symbol }}{% if name %} ? {{ name }}{% endif %}">"""

new = """<img class="tr-chart trade-chart-img"
         src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else '') }}{% if trade is defined and trade and trade.open_date %}&buy_ts={{ (trade.open_date|string)|urlencode }}&ts={{ (trade.open_date|string)|urlencode }}{% endif %}{% if trade is defined and trade and trade.close_date and (trade.price_sold or 0) %}&sell_ts={{ (trade.close_date|string)|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"
         alt="Trade chart {{ trade.symbol }}{% if name %} ? {{ name }}{% endif %}">"""

if old in txt:
    txt = txt.replace(old, new, 1)
else:
    pat = re.compile(r'<img class="tr-chart trade-chart-img"\s+src="/trade_review/chart\?symbol=\{\{.*?\}\}.*?alt="Trade chart .*?">', re.S)
    m = pat.search(txt)
    if not m:
        raise SystemExit("Could not find target chart <img> tag to patch.")
    txt = txt[:m.start()] + new + txt[m.end():]

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("Marker: MM_TRV_CHART_PARAMS_V1")
