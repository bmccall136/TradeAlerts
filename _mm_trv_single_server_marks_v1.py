import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_server_marks_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

# 1) Ensure server-side mark strings exist right after _buy_ts/_sell_ts block
needle = """{% if sell_triggers and (sell_triggers|length) > 0 %}
  {% set _s0 = sell_triggers[0] %}
  {% set _sell_ts = (_s0.ts_et or _s0.time_et or '') %}
{% endif %}
<!-- /MM_TRV_CHART_BUY_SELL_PARAMS_V1 -->"""

insert = """{% if sell_triggers and (sell_triggers|length) > 0 %}
  {% set _s0 = sell_triggers[0] %}
  {% set _sell_ts = (_s0.ts_et or _s0.time_et or '') %}
{% endif %}
{% set _buy_marks = [] %}
{% if buy_triggers and (buy_triggers|length) > 0 %}
  {% for _t in buy_triggers %}
    {% if _t.ts_et or _t.time_et %}
      {% set _buy_marks = _buy_marks + [(_t.ts_et or _t.time_et)] %}
    {% endif %}
  {% endfor %}
{% endif %}
{% set _sell_marks = [] %}
{% if sell_triggers and (sell_triggers|length) > 0 %}
  {% for _t in sell_triggers %}
    {% if _t.ts_et or _t.time_et %}
      {% set _sell_marks = _sell_marks + [(_t.ts_et or _t.time_et)] %}
    {% endif %}
  {% endfor %}
{% endif %}
<!-- /MM_TRV_CHART_BUY_SELL_PARAMS_V1 -->"""

if needle in txt and "_buy_marks" not in txt:
    txt = txt.replace(needle, insert, 1)

# 2) Replace the chart img block with one that passes buy_marks / sell_marks
pat = re.compile(r'<img class="tr-chart trade-chart-img"[\s\S]*?alt="Trade chart .*?">', re.I)

new_block = """<img class="tr-chart trade-chart-img"
         src="/trade_review/chart?symbol={{ symbol if symbol is defined else (trade.symbol if trade is defined and trade else '') }}{% if _buy_ts %}&buy_ts={{ _buy_ts|urlencode }}&ts={{ _buy_ts|urlencode }}{% endif %}{% if _sell_ts %}&sell_ts={{ _sell_ts|urlencode }}{% endif %}{% if _buy_marks and (_buy_marks|length) > 0 %}&buy_marks={{ (_buy_marks|join('|'))|urlencode }}{% endif %}{% if _sell_marks and (_sell_marks|length) > 0 %}&sell_marks={{ (_sell_marks|join('|'))|urlencode }}{% endif %}&v={{ (trade.ts_utc if trade is defined and trade and trade.ts_utc else (trade_id if trade_id else 0)) }}"
         alt="Trade chart {{ trade.symbol }}{% if name %} ? {{ name }}{% endif %}">"""

m = pat.search(txt)
if not m:
    raise SystemExit("Could not find chart img block")
txt = txt[:m.start()] + new_block + txt[m.end():]

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_SINGLE_SERVER_MARKS_V1")
