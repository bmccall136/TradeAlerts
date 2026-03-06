import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_runtime_sell_fallback_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """    const buyTs = (j.meta && j.meta.anchor_buy_time_et) ? String(j.meta.anchor_buy_time_et).trim() : (buyTimes[0] || "");
    const sellTs = (j.meta && j.meta.anchor_sell_time_et) ? String(j.meta.anchor_sell_time_et).trim() : (sellTimes[0] || "");"""

new = """    const buyTs = (j.meta && j.meta.anchor_buy_time_et) ? String(j.meta.anchor_buy_time_et).trim() : (buyTimes[0] || "");

    let sellTs = (j.meta && j.meta.anchor_sell_time_et) ? String(j.meta.anchor_sell_time_et).trim() : "";
    if(!sellTs){
      const sells = Array.isArray(j.sells) ? j.sells : [];
      const tradeIdStr = String(tradeId || "").trim();
      const symbolFromMeta = String((j.meta && j.meta.symbol) || "").trim().toUpperCase();

      let srow = null;

      if(tradeIdStr){
        srow = sells.find(r => String((r && r.trade_id) || "").trim() === tradeIdStr) || null;
      }
      if(!srow && symbolFromMeta){
        srow = sells.find(r => String((r && r.symbol) || "").trim().toUpperCase() === symbolFromMeta) || null;
      }
      if(!srow && sells.length){
        srow = sells[0];
      }

      if(srow){
        sellTs = String((srow.time_et || srow.ts_et || "")).trim();
      }
    }

    if(!sellTs){
      sellTs = (sellTimes[0] || "");
    }"""

if old not in txt:
    raise SystemExit("Target buyTs/sellTs block not found")

txt = txt.replace(old, new, 1)
P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_RUNTIME_SELL_FALLBACK_V1")
