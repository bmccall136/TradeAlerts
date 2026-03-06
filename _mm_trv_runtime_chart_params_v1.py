import pathlib, shutil, datetime

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

inject = r"""
<!-- MM_TRV_RUNTIME_CHART_PARAMS_V1 -->
<script>
(function(){
  function q(sel){ return document.querySelector(sel); }
  function qq(sel){ return Array.from(document.querySelectorAll(sel)); }
  function enc(s){ return encodeURIComponent((s||"").trim()); }

  function firstTimestampUnderHeader(headerText){
    const headers = qq("h1,h2,h3,h4,div,span,strong");
    const hdr = headers.find(el => ((el.textContent||"").trim() === headerText));
    if(!hdr) return "";
    let n = hdr.nextElementSibling;
    while(n){
      const txt = (n.textContent || "").trim();
      const m = txt.match(/\b(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\b/);
      if(m) return m[1];
      if(/^(Buy Triggers|Sell Triggers|Signal Fires)$/i.test(txt)) break;
      n = n.nextElementSibling;
    }
    return "";
  }

  function patch(){
    const img = q("img.tr-chart");
    if(!img) return;

    let src = img.getAttribute("src") || "";
    if(!src || src.indexOf("/trade_review/chart") === -1) return;
    if(src.indexOf("buy_ts=") !== -1) return;

    const buyTs = firstTimestampUnderHeader("Buy Triggers");
    const sellTs = firstTimestampUnderHeader("Sell Triggers");

    if(!buyTs) return;

    const joiner = src.indexOf("?") >= 0 ? "&" : "?";
    src += joiner + "buy_ts=" + enc(buyTs) + "&ts=" + enc(buyTs);
    if(sellTs) src += "&sell_ts=" + enc(sellTs);
    src += "&rtfix=1";

    img.setAttribute("src", src);
    try { console.log("MM_TRV_RUNTIME_CHART_PARAMS_V1", src); } catch(e) {}
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", function(){
      setTimeout(patch, 50);
      setTimeout(patch, 250);
      setTimeout(patch, 800);
    });
  } else {
    setTimeout(patch, 50);
    setTimeout(patch, 250);
    setTimeout(patch, 800);
  }
})();
</script>
"""

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

for p in targets:
    if not p.exists():
        print(f"SKIP missing -> {p}")
        continue
    txt = p.read_text(encoding="utf-8", errors="replace")
    bak = p.with_name(p.name + f".bak_runtime_chart_params_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    if "MM_TRV_RUNTIME_CHART_PARAMS_V1" in txt:
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
