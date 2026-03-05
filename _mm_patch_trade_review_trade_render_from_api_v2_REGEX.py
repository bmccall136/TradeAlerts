import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_trade.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_trade_api_v2REGEX_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_TRADE_RENDER_FROM_API_V2"
if MARK in txt:
    print("Already patched (V2 marker present).")
    raise SystemExit(0)

# Match V1 markers with ANY whitespace
start_re = re.compile(r"<!--\s*MM_TRV_TRADE_RENDER_FROM_API_V1\s*-->", re.I)
end_re   = re.compile(r"<!--\s*/\s*MM_TRV_TRADE_RENDER_FROM_API_V1\s*-->", re.I)

m1 = start_re.search(txt)
m2 = end_re.search(txt, m1.end() if m1 else 0)

block = """<!-- __MARK__ -->
<script>
(function(){
  try{
    var m = String(window.location.pathname||"").match(/\\/trade_review\\/trade\\/(\\d+)/i);
    if(!m) return;
    var trade_id = m[1] || "";
    if(!trade_id) return;

    function esc(s){
      return String(s||"").replace(/[&<>\"']/g, function(c){
        return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c];
      });
    }

    function renderList(rows){
      if(!rows || !rows.length) return "<div class='mm-muted'>No triggers found.</div>";
      return rows.map(function(r){
        var t = esc(r.time_et || "");
        var p = (r.price!=null) ? ("$" + Number(r.price).toFixed(2)) : "";
        var s = esc(r.signals_pretty || "");
        return "<div class='mm-trv-row'><div class='mm-trv-line1'><span class='mm-trv-time'>" + t +
               "</span><span class='mm-trv-price'>" + p + "</span></div><div class='mm-trv-sig'>" + s + "</div></div>";
      }).join("");
    }

    function ensureBox(id){
      var box = document.getElementById(id);
      if(box) return box;
      box = document.createElement("div");
      box.id = id;
      return box;
    }

    function findTriggersSection(which){
      var blocks = Array.from(document.querySelectorAll(".tr-triggers-block"));
      if(blocks.length >= 2){
        if(which === "buy") return blocks[0];
        if(which === "sell") return blocks[1];
      }
      var hdr = Array.from(document.querySelectorAll("h1,h2,h3,h4")).find(function(el){
        return new RegExp("^" + which + "\\\\s+triggers", "i").test((el.textContent||"").trim());
      });
      if(!hdr) return null;
      return hdr.parentElement || null;
    }

    function clearNoTriggersText(root){
      if(!root) return;
      Array.from(root.querySelectorAll(".tr-empty")).forEach(function(el){ el.style.display="none"; });
      Array.from(root.querySelectorAll("*")).forEach(function(el){
        if(el.childElementCount !== 0) return;
        var t = (el.textContent||"").trim();
        if(/^No (buy|sell) triggers found\\.?$/i.test(t)) el.textContent = "";
      });
    }

    function setMeta(meta){
      try{
        var sub = document.querySelector(".tr-sub");
        if(!sub) return;
        var spans = Array.from(sub.querySelectorAll("span"));
        var buyPx = meta.anchor_buy_price;
        var sellPx = meta.anchor_sell_price;
        var qty = meta.anchor_qty;

        spans.forEach(function(sp){
          var t = (sp.textContent||"").trim();
          if(/^Buy:\\s*@/i.test(t) && buyPx!=null) sp.textContent = "Buy:  @ " + Number(buyPx).toFixed(2);
          if(/^Sell:\\s*@/i.test(t) && sellPx!=null) sp.textContent = "Sell:  @ " + Number(sellPx).toFixed(2);
          if(/^Qty:\\s*/i.test(t) && qty!=null) sp.textContent = "Qty: " + qty;
        });
      }catch(_e){}
    }

    fetch("/api/trade_review?trade_id=" + encodeURIComponent(trade_id), {cache:"no-store"})
      .then(function(res){ return res.ok ? res.json() : Promise.reject("HTTP " + res.status); })
      .then(function(j){
        var buyRows = j.buy_triggers || [];
        var sellRows = j.sell_triggers || [];
        var meta = j.meta || {};

        var buyRoot = findTriggersSection("buy");
        if(buyRoot){
          var buyBox = ensureBox("mm-trv-buy-box");
          if(!buyBox.parentElement) buyRoot.prepend(buyBox);
          buyBox.innerHTML = renderList(buyRows);
          if(buyRows.length) clearNoTriggersText(buyRoot);
        }

        var sellRoot = findTriggersSection("sell");
        if(sellRoot){
          var sellBox = ensureBox("mm-trv-sell-box");
          if(!sellBox.parentElement) sellRoot.prepend(sellBox);
          sellBox.innerHTML = renderList(sellRows);
          if(sellRows.length) clearNoTriggersText(sellRoot);
        }

        setMeta(meta);
      })
      .catch(function(err){
        console.log("__MARK__ fetch failed:", err);
      });
  }catch(e){
    console.log("__MARK__ exception:", e);
  }
})();
</script>

<style>
  .mm-trv-row{margin:6px 0;padding:6px 10px;border:1px solid rgba(255,255,255,.10);border-radius:10px;background:rgba(255,255,255,.04)}
  .mm-trv-line1{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .mm-trv-time{display:inline-block;min-width:170px;opacity:.9}
  .mm-trv-price{display:inline-block;min-width:70px;opacity:.95;font-weight:800}
  .mm-trv-sig{margin-top:4px;opacity:.95}
  .mm-muted{opacity:.65}
</style>
<!-- /__MARK__ -->""".replace("__MARK__", MARK)

if m1 and m2 and m2.start() > m1.end():
    # Replace V1 block with V2 block
    txt2 = txt[:m1.start()] + block + "\n" + txt[m2.end():]
    P.write_text(txt2, encoding="utf-8", errors="replace")
    print("PATCHED (replaced V1 block) ->", P)
    raise SystemExit(0)

# Fallback: inject before </body> if markers missing
low = txt.lower()
ins = "\n\n" + block + "\n\n"
if "</body>" in low:
    k = low.rfind("</body>")
    txt2 = txt[:k] + ins + txt[k:]
elif "</html>" in low:
    k = low.rfind("</html>")
    txt2 = txt[:k] + ins + txt[k:]
else:
    txt2 = txt + ins

P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED (injected fallback) ->", P)
