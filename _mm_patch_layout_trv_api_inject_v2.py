import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\layout.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_layout_api_inject_v2_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

START = "<!-- MM_TRV_LAYOUT_API_INJECT_V1 -->"
END   = "<!-- /MM_TRV_LAYOUT_API_INJECT_V1 -->"

i = txt.find(START)
j = txt.find(END, i+1)
if i < 0 or j < 0 or j <= i:
    raise SystemExit("ERROR: V1 markers not found in layout.html (file drift).")

MARK = "MM_TRV_LAYOUT_API_INJECT_V2"
if MARK in txt:
    print("Already patched (V2 marker present).")
    raise SystemExit(0)

block = f"""<!-- {MARK} -->
<script>
(function(){
  function ready(fn){
    if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(function(){
    try{
      var path = String(window.location.pathname||"");
      var m = path.match(/\\/trade_review\\/trade\\/(\\d+)/i);
      if(!m) return;

      var trade_id = m[1] || "";
      if(!trade_id) return;

      function esc(s){
        return String(s||"").replace(/[&<>\"']/g, function(c){
          return {{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c];
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

      function mountIntoBlocks(buyRows, sellRows){
        var blocks = Array.from(document.querySelectorAll(".tr-triggers-block"));
        if(blocks.length >= 1){
          var buyBox = ensureBox("mm-trv-buy-box");
          if(!buyBox.parentElement) blocks[0].prepend(buyBox);
          buyBox.innerHTML = renderList(buyRows);
          if(buyRows.length) clearNoTriggersText(blocks[0]);
        }
        if(blocks.length >= 2){
          var sellBox = ensureBox("mm-trv-sell-box");
          if(!sellBox.parentElement) blocks[1].prepend(sellBox);
          sellBox.innerHTML = renderList(sellRows);
          if(sellRows.length) clearNoTriggersText(blocks[1]);
        }
      }

      fetch("/api/trade_review?trade_id=" + encodeURIComponent(trade_id), {{cache:"no-store"}})
        .then(function(res){ return res.ok ? res.json() : Promise.reject("HTTP " + res.status); })
        .then(function(j){
          var buyRows = j.buy_triggers || [];
          var sellRows = j.sell_triggers || [];
          var meta = j.meta || {{}};
          mountIntoBlocks(buyRows, sellRows);
          setMeta(meta);
        })
        .catch(function(err){
          console.log("{MARK} fetch failed:", err);
        });
    }catch(e){
      console.log("{MARK} exception:", e);
    }
  });
})();
</script>

<style>
  .mm-trv-row{{margin:6px 0;padding:6px 10px;border:1px solid rgba(255,255,255,.10);border-radius:10px;background:rgba(255,255,255,.04)}}
  .mm-trv-line1{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
  .mm-trv-time{{display:inline-block;min-width:170px;opacity:.9}}
  .mm-trv-price{{display:inline-block;min-width:70px;opacity:.95;font-weight:800}}
  .mm-trv-sig{{margin-top:4px;opacity:.95}}
  .mm-muted{{opacity:.65}}
</style>
<!-- /{MARK} -->"""

# Replace the V1 block with the V2 block (keep the START/END markers for easy future edits)
txt2 = txt[:i] + START + "\n" + block + "\n" + END + txt[j+len(END):]

P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
