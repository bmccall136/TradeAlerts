import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_cleanup_runtime_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

# 1) Remove anything before {% extends ... %} to stop Quirks Mode
m = re.search(r'\{%\s*extends\s+"layout\.html"\s*%\}', txt)
if not m:
    raise SystemExit('Could not find {% extends "layout.html" %}')
txt = txt[m.start():]

# 2) Replace the runtime API patcher with a clean single-run version
pat = re.compile(r'<!-- MM_TRV_RUNTIME_MARKS_FROM_API_V1 -->[\s\S]*?</script>\s*', re.I)

new_block = r'''<!-- MM_TRV_RUNTIME_MARKS_FROM_API_V2_CLEAN -->
<script>
(function(){
  if (window.__MM_TRV_RUNTIME_MARKS_FROM_API_V2_CLEAN__) return;
  window.__MM_TRV_RUNTIME_MARKS_FROM_API_V2_CLEAN__ = 1;

  function q(sel){ return document.querySelector(sel); }

  function getTradeIdFromPath(){
    const m = String(window.location.pathname || "").match(/\/trade_review\/trade\/(\d+)/i);
    return m ? m[1] : "";
  }

  async function patch(){
    const img = q("img.tr-chart");
    if(!img) return;
    if (img.dataset.mmPatched === "1") return;

    const tradeId = getTradeIdFromPath();
    if(!tradeId) return;

    let j = null;
    try{
      const res = await fetch("/api/trade_review?trade_id=" + encodeURIComponent(tradeId), { cache: "no-store" });
      if(!res.ok) return;
      j = await res.json();
    }catch(e){
      return;
    }
    if(!j) return;

    const buyRows = Array.isArray(j.buy_triggers) ? j.buy_triggers : [];
    const sellRows = Array.isArray(j.sell_triggers) ? j.sell_triggers : [];

    const buyTimes = Array.from(new Set(
      buyRows.map(r => String((r && (r.time_et || r.ts_et || "")) || "").trim()).filter(Boolean)
    ));
    const sellTimes = Array.from(new Set(
      sellRows.map(r => String((r && (r.time_et || r.ts_et || "")) || "").trim()).filter(Boolean)
    ));

    const buyTs = (j.meta && j.meta.anchor_buy_time_et) ? String(j.meta.anchor_buy_time_et).trim() : (buyTimes[0] || "");
    const sellTs = (j.meta && j.meta.anchor_sell_time_et) ? String(j.meta.anchor_sell_time_et).trim() : (sellTimes[0] || "");

    const u = new URL(img.getAttribute("src") || "", window.location.origin);
    u.searchParams.delete("ts");
    u.searchParams.delete("buy_ts");
    u.searchParams.delete("sell_ts");
    u.searchParams.delete("buy_marks");
    u.searchParams.delete("sell_marks");
    u.searchParams.delete("rtfix");

    if (buyTs) {
      u.searchParams.set("buy_ts", buyTs);
      u.searchParams.set("ts", buyTs);
    }
    if (sellTs) u.searchParams.set("sell_ts", sellTs);
    if (buyTimes.length) u.searchParams.set("buy_marks", buyTimes.join("|"));
    if (sellTimes.length) u.searchParams.set("sell_marks", sellTimes.join("|"));
    u.searchParams.set("rtfix", "1");

    const newSrc = u.pathname + "?" + u.searchParams.toString();
    img.setAttribute("src", newSrc);
    img.dataset.mmPatched = "1";

    try { console.log("MM_TRV_RUNTIME_MARKS_FROM_API_V2_CLEAN", newSrc, {buyTimes, sellTimes, buyTs, sellTs}); } catch(e) {}
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", patch, { once:true });
  } else {
    patch();
  }
})();
</script>
'''

txt, n = pat.subn(new_block + "\n", txt, count=1)
if n == 0:
    raise SystemExit("Could not find MM_TRV_RUNTIME_MARKS_FROM_API_V1 block to replace")

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_RUNTIME_MARKS_FROM_API_V2_CLEAN")
