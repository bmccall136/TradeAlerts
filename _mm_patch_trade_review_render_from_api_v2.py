import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_api_render_v2_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_RENDER_FROM_API_V2"
if MARK in txt:
    print("Already patched (marker present).")
    raise SystemExit(0)

js = r"""
<!-- %s -->
<script>
(function(){
  function qs(k){ try { return new URLSearchParams(window.location.search).get(k) || ""; } catch(e){ return ""; } }
  var symbol = (qs("symbol") || "").toUpperCase();
  var ts     = (qs("ts") || "").trim();
  if(!symbol || !ts){ return; }

  function esc(s){ return String(s||"").replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]; }); }
  function renderList(rows){
    if(!rows || !rows.length) return "<div class='mm-muted'>No triggers found.</div>";
    return rows.map(function(r){
      var t = esc(r.time_et || "");
      var p = (r.price!=null) ? ("$" + Number(r.price).toFixed(2)) : "";
      var s = esc(r.signals_pretty || "");
      return "<div class='mm-trv-row'><span class='mm-trv-time'>" + t + "</span> <span class='mm-trv-price'>" + p + "</span><div class='mm-trv-sig'>" + s + "</div></div>";
    }).join("");
  }

  fetch("/api/trade_review?symbol=" + encodeURIComponent(symbol) + "&ts=" + encodeURIComponent(ts))
    .then(function(res){ return res.ok ? res.json() : Promise.reject("HTTP " + res.status); })
    .then(function(j){
      var buyHdr  = Array.from(document.querySelectorAll("h1,h2,h3,h4,div,strong,span")).find(el => /buy triggers/i.test((el.textContent||"").trim()));
      var sellHdr = Array.from(document.querySelectorAll("h1,h2,h3,h4,div,strong,span")).find(el => /sell triggers/i.test((el.textContent||"").trim()));

      if(buyHdr){
        var box = document.getElementById("mm-trv-buy-box");
        if(!box){
          box = document.createElement("div");
          box.id = "mm-trv-buy-box";
          buyHdr.insertAdjacentElement("afterend", box);
        }
        box.innerHTML = renderList(j.buy_triggers || []);
      }

      if(sellHdr){
        var box2 = document.getElementById("mm-trv-sell-box");
        if(!box2){
          box2 = document.createElement("div");
          box2.id = "mm-trv-sell-box";
          sellHdr.insertAdjacentElement("afterend", box2);
        }
        box2.innerHTML = renderList(j.sell_triggers || []);
      }

      // Update the "Buy: @ 0.00" line if present
      var meta = j.meta || {};
      var lines = Array.from(document.querySelectorAll("body *")).filter(el => (el.childElementCount===0) && /Buy:\s*@/i.test(el.textContent||"") && /Sell:\s*@/i.test(el.textContent||""));
      if(lines.length){
        var el = lines[0];
        var bp = meta.anchor_buy_price;
        var qt = meta.anchor_qty;
        if(bp!=null){
          var s = el.textContent || "";
          s = s.replace(/Buy:\s*@\s*0\.00/i, "Buy: @ " + Number(bp).toFixed(2));
          if(qt!=null) s = s.replace(/Qty:\s*[0-9.]+/i, "Qty: " + qt);
          el.textContent = s;
        }
      }
    })
    .catch(function(err){
      console.log("%s fetch failed:", err);
    });
})();
</script>
<style>
  .mm-trv-row{margin:6px 0;padding:6px 8px;border:1px solid rgba(255,255,255,.10);border-radius:10px;background:rgba(255,255,255,.04)}
  .mm-trv-time{display:inline-block;min-width:170px;opacity:.9}
  .mm-trv-price{display:inline-block;min-width:70px;opacity:.95}
  .mm-trv-sig{margin-top:4px;opacity:.95}
  .mm-muted{opacity:.65}
</style>
<!-- /%s -->
""" % (MARK, MARK, MARK)

lower = txt.lower()

if "</html" in lower:
    txt2 = re.sub(r"(?is)</html\s*>", js + "\n</html>", txt, count=1)
else:
    txt2 = txt.rstrip() + "\n\n" + js + "\n"

P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
