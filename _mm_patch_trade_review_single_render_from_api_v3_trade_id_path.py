import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_api_render_v3_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

START = "<!-- MM_TRV_RENDER_FROM_API_V2 -->"
END   = "<!-- /MM_TRV_RENDER_FROM_API_V2 -->"

if START not in txt or END not in txt:
    print("ERROR: V2 markers not found; file drift. Not patched.")
    raise SystemExit(1)

block = r"""<!-- MM_TRV_RENDER_FROM_API_V3 -->
<script>
(function(){
  function qs(k){ try { return new URLSearchParams(window.location.search).get(k) || ""; } catch(e){ return ""; } }

  // Prefer canonical trade_id from path /trade_review/trade/<id>
  var m = String(window.location.pathname||"").match(/\/trade_review\/trade\/(\d+)/i);
  var trade_id = m ? m[1] : "";

  // Legacy: symbol+ts query params
  var symbol = (qs("symbol") || "").toUpperCase();
  var tsq    = (qs("ts") || "").trim();

  // Decide which API to call
  var apiUrl = "";
  if(trade_id){
    apiUrl = "/api/trade_review?trade_id=" + encodeURIComponent(trade_id);
  }else if(symbol && tsq){
    apiUrl = "/api/trade_review?symbol=" + encodeURIComponent(symbol) + "&ts=" + encodeURIComponent(tsq);
  }else{
    return; // nothing to render
  }

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

  function ensureBox(id, afterEl){
    var box = document.getElementById(id);
    if(box) return box;
    box = document.createElement("div");
    box.id = id;
    if(afterEl && afterEl.insertAdjacentElement){
      afterEl.insertAdjacentElement("afterend", box);
    }else{
      document.body.appendChild(box);
    }
    return box;
  }

  fetch(apiUrl)
    .then(function(res){ return res.ok ? res.json() : Promise.reject("HTTP " + res.status); })
    .then(function(j){
      // Try explicit placeholders first (if they exist)
      var buyBox = document.getElementById("mm-trv-buy-box");
      var sellBox = document.getElementById("mm-trv-sell-box");

      // Fallback: find headings and inject boxes
      if(!buyBox){
        var buyHdr = Array.from(document.querySelectorAll("h1,h2,h3,h4,div,strong,span")).find(function(el){
          return /buy triggers/i.test((el.textContent||"").trim());
        });
        if(buyHdr) buyBox = ensureBox("mm-trv-buy-box", buyHdr);
      }
      if(!sellBox){
        var sellHdr = Array.from(document.querySelectorAll("h1,h2,h3,h4,div,strong,span")).find(function(el){
          return /sell triggers/i.test((el.textContent||"").trim());
        });
        if(sellHdr) sellBox = ensureBox("mm-trv-sell-box", sellHdr);
      }

      if(buyBox)  buyBox.innerHTML  = renderList(j.buy_triggers || []);
      if(sellBox) sellBox.innerHTML = renderList(j.sell_triggers || []);

      // Update the header line: Buy/Sell/Qty (handles 0.00 display)
      var meta = j.meta || {};
      var lines = Array.from(document.querySelectorAll("body *")).filter(function(el){
        return (el.childElementCount===0) && /Buy:\s*@/i.test(el.textContent||"") && /Qty:\s*/i.test(el.textContent||"");
      });
      if(lines.length){
        var el = lines[0];
        var bp = meta.anchor_buy_price;
        var sp = meta.anchor_sell_price;
        var qt = meta.anchor_qty;

        var s = el.textContent || "";
        if(bp!=null) s = s.replace(/Buy:\s*@\s*0\.00/i, "Buy: @ " + Number(bp).toFixed(2));
        if(sp!=null) s = s.replace(/Sell:\s*@\s*0\.00/i, "Sell: @ " + Number(sp).toFixed(2));
        if(qt!=null) s = s.replace(/Qty:\s*[0-9.]+/i, "Qty: " + qt);
        el.textContent = s;
      }
    })
    .catch(function(err){
      console.log("MM_TRV_RENDER_FROM_API_V3 fetch failed:", err);
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
<!-- /MM_TRV_RENDER_FROM_API_V3 -->"""

# replace the whole V2 block
pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
txt2 = pat.sub(block, txt, count=1)

P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
