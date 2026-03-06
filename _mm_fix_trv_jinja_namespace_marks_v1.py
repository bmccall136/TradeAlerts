import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_jinja_namespace_marks_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

pat = re.compile(
    r'\{% set _buy_marks = \[\] %\}[\s\S]*?\{% set _sell_marks = \[\] %\}[\s\S]*?<!-- /MM_TRV_CHART_BUY_SELL_PARAMS_V1 -->',
    re.M
)

new_block = """{% set _bm = namespace(vals=[]) %}
{% if buy_triggers and (buy_triggers|length) > 0 %}
  {% for _t in buy_triggers %}
    {% if _t.ts_et or _t.time_et %}
      {% set _bm.vals = _bm.vals + [(_t.ts_et or _t.time_et)] %}
    {% endif %}
  {% endfor %}
{% endif %}
{% set _buy_marks = _bm.vals %}

{% set _sm = namespace(vals=[]) %}
{% if sell_triggers and (sell_triggers|length) > 0 %}
  {% for _t in sell_triggers %}
    {% if _t.ts_et or _t.time_et %}
      {% set _sm.vals = _sm.vals + [(_t.ts_et or _t.time_et)] %}
    {% endif %}
  {% endfor %}
{% endif %}
{% set _sell_marks = _sm.vals %}
<!-- /MM_TRV_CHART_BUY_SELL_PARAMS_V1 -->"""

txt2, n = pat.subn(new_block, txt, count=1)
if n == 0:
    raise SystemExit("Could not find _buy_marks/_sell_marks block to replace.")

P.write_text(txt2, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_JINJA_NAMESPACE_MARKS_V1")
