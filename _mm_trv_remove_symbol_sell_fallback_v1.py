import pathlib, shutil, datetime

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_remove_symbol_sell_fallback_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """          if(!_match && _symbol){
            _match = _sells.find(function(r){
              return String((r && r.symbol || "")).trim().toUpperCase() === _symbol;
            }) || null;
          }
          if(!_match && _sells.length){
            _match = _sells[0];
          }"""

new = """          // DO NOT fall back by symbol here.
          // A buy review for a symbol may have a later unrelated sell row,
          // which wrongly makes the buy review look like a closed sell review.
          // Only use an exact trade_id match for sell fallback."""

if old not in txt:
    raise SystemExit("Target symbol sell fallback block not found")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_REMOVE_SYMBOL_SELL_FALLBACK_V1")
