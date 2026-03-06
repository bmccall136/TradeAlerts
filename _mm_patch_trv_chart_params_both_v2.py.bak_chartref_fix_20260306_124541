import pathlib, shutil, datetime, re

FILES = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_trade.html"),
]

NEW_TAG = """<img class="tr-chart trade-chart-img"
         src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else '') }}{% if trade is defined and trade and trade.open_date %}&buy_ts={{ (trade.open_date|string)|urlencode }}&ts={{ (trade.open_date|string)|urlencode }}{% endif %}{% if trade is defined and trade and trade.close_date and (trade.price_sold or 0) %}&sell_ts={{ (trade.close_date|string)|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"
         alt="Trade chart {{ trade.symbol }}{% if name %} ? {{ name }}{% endif %}">"""

PAT = re.compile(
    r'<img class="tr-chart trade-chart-img"\s+src="/trade_review/chart\?symbol=\{\{.*?\}\}.*?alt="Trade chart .*?">',
    re.S
)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

for P in FILES:
    if not P.exists():
        print(f"SKIP missing -> {P}")
        continue

    txt = P.read_text(encoding="utf-8", errors="replace")
    bak = P.with_name(P.name + f".bak_chart_params_both_v2_{ts}")
    shutil.copy2(P, bak)
    print(f"Backup -> {bak}")

    new_txt, n = PAT.subn(NEW_TAG, txt, count=1)
    if n == 0:
        print(f"NO_MATCH -> {P}")
        continue

    if new_txt == txt:
        print(f"UNCHANGED -> {P}")
        continue

    P.write_text(new_txt, encoding="utf-8", newline="\n")
    print(f"PATCHED -> {P}")
    patched += 1

print(f"PATCH_COUNT={patched}")
if patched == 0:
    raise SystemExit("No templates patched.")
