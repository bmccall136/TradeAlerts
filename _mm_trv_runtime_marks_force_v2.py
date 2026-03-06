import pathlib, shutil, datetime

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

marker = "MM_TRV_RUNTIME_MARKS_FORCE_V2"

inject = r"""
<!-- MM_TRV_RUNTIME_MARKS_FORCE_V2 -->
<script>
(function(){
  function q(sel){ return document.querySelector(sel); }
  function qq(sel){ return Array.from(document.querySelectorAll(sel)); }
  function enc(s){ return encodeURIComponent((s||"").trim()); }

  function collectTriggerTimes(headerText){
    const out = [];
    const headers = qq("h1,h2,h3,h4,div,span,strong");
    const hdr = headers.find(el => ((el.textContent||"").trim() === headerText));
    if(!hdr) return out;

    let n = hdr.nextElementSibling;
    while(n){
      const txt = (n.textContent || "").trim();

      if(/^(Buy Triggers|Sell Triggers|Signal Fires)$/i.test(txt)) break;

      const matches = txt.match(/\b20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b/g);
      if(matches){
        matches.forEach(v => out.push(v));
      }

      n = n.nextElementSibling;
    }
    return Array.from(new Set(out));
  }

  function patch(){
    const img = q("img.tr-chart");
    if(!img) return;

    let src = img.getAttribute("src") || "";
    if(!src || src.indexOf("/trade_review/chart") === -1) return;

    const buyTimes = collectTriggerTimes("Buy Triggers");
    const sellTimes = collectTriggerTimes("Sell Triggers");

    if(!buyTimes.length && !sellTimes.length) return;

    src = src.replace(/([&?])buy_marks=[^&]*/g, "");
    src = src.replace(/([&?])sell_marks=[^&]*/g, "");
    src = src.replace(/[?&]rtfix=1/g, "");

    const joiner = src.indexOf("?") >= 0 ? "&" : "?";
    let extra = "";
    if(buyTimes.length) extra += "&buy_marks=" + buyTimes.map(enc).join("|");
    if(sellTimes.length) extra += "&sell_marks=" + sellTimes.map(enc).join("|");
    extra += "&rtfix=1";

    src = src + joiner + extra.replace(/^&/, "");
    img.setAttribute("src", src);

    try { console.log("MM_TRV_RUNTIME_MARKS_FORCE_V2", src, {buyTimes, sellTimes}); } catch(e) {}
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
    bak = p.with_name(p.name + f".bak_runtime_marks_force_v2_{ts}")
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
