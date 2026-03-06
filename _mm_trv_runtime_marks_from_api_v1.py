import pathlib, shutil, datetime

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

marker = "MM_TRV_RUNTIME_MARKS_FROM_API_V1"

inject = r"""
<!-- MM_TRV_RUNTIME_MARKS_FROM_API_V1 -->
<script>
(function(){
  function q(sel){ return document.querySelector(sel); }
  function enc(s){ return encodeURIComponent((s||"").trim()); }

  function getTradeIdFromPath(){
    const m = String(window.location.pathname || "").match(/\/trade_review\/trade\/(\d+)/i);
    return m ? m[1] : "";
  }

  async function patch(){
    const img = q("img.tr-chart");
    if(!img) return;

    let src = img.getAttribute("src") || "";
    if(!src || src.indexOf("/trade_review/chart") === -1) return;

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
      buyRows.map(r => (r && (r.time_et || r.ts_et || "") || "").trim()).filter(Boolean)
    ));
    const sellTimes = Array.from(new Set(
      sellRows.map(r => (r && (r.time_et || r.ts_et || "") || "").trim()).filter(Boolean)
    ));

    const buyTs = (j.meta && j.meta.anchor_buy_time_et) ? String(j.meta.anchor_buy_time_et).trim() : (buyTimes[0] || "");
    const sellTs = (j.meta && j.meta.anchor_sell_time_et) ? String(j.meta.anchor_sell_time_et).trim() : (sellTimes[0] || "");

    src = src.replace(/([&?])buy_ts=[^&]*/g, "");
    src = src.replace(/([&?])sell_ts=[^&]*/g, "");
    src = src.replace(/([&?])buy_marks=[^&]*/g, "");
    src = src.replace(/([&?])sell_marks=[^&]*/g, "");
    src = src.replace(/[?&]rtfix=1/g, "");

    const joiner = src.indexOf("?") >= 0 ? "&" : "?";
    let extra = "";
    if(buyTs) extra += "&buy_ts=" + enc(buyTs) + "&ts=" + enc(buyTs);
    if(sellTs) extra += "&sell_ts=" + enc(sellTs);
    if(buyTimes.length) extra += "&buy_marks=" + buyTimes.map(enc).join("|");
    if(sellTimes.length) extra += "&sell_marks=" + sellTimes.map(enc).join("|");
    extra += "&rtfix=1";

    src = src + joiner + extra.replace(/^&/, "");
    img.setAttribute("src", src);

    try { console.log("MM_TRV_RUNTIME_MARKS_FROM_API_V1", src, {buyTimes, sellTimes, buyTs, sellTs}); } catch(e) {}
  }

  function runMany(){
    setTimeout(patch, 50);
    setTimeout(patch, 250);
    setTimeout(patch, 800);
    setTimeout(patch, 1500);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", runMany);
  } else {
    runMany();
  }
})();
</script>
"""

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

for p in targets:
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8", errors="replace")
    bak = p.with_name(p.name + f".bak_runtime_marks_from_api_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    if marker in txt:
      print(f"UNCHANGED -> {p}")
      continue

    if "{% endblock %}" in txt:
      txt = txt.replace("{% endblock %}", inject + "\n\n{% endblock %}", 1)
      p.write_text(txt, encoding="utf-8", newline="\n")
      print(f"PATCHED -> {p}")
      patched += 1
    else:
      print(f"NO_END_BLOCK -> {p}")

print(f"PATCH_COUNT={patched}")
if patched == 0:
    raise SystemExit("Nothing patched")
