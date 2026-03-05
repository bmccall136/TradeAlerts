import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\templates\layout.html")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".html.bak_trv_layout_api_inject_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_LAYOUT_API_INJECT_V1"
if MARK in txt:
    print("Already patched (marker present).")
    raise SystemExit(0)

block = r"""
<!-- %s -->
<script>
(function(){
  try{
    var path = String(window.location.pathname||"");
    var m = path.match(/\/trade_review\/trade\/(\d+)/i);
    if(!m) return;

    var trade_id = m[1] || "";
    if(!trade_id) return;

    function esc(s){
      return String(s||"").replace(/[&<>"']/g, function(c){
        return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
      });
    }

    function renderList(rows){
      if(!rows || !rows.length) return "<div class='mm-muted'>No triggers found.</div>";
      return rows.map(function(r){
        var t = esc(r.time_et || "");
        var p = (r.price!=null) ? ("$" + Number(r.price).toFixed(2)) : "";
        var s = esc(r.signals_pretty || "");
        return "<div class='mm-trv-row'><span class='mm-trv-time'>" + t + "</span> <span class='mm-trv-price'>" + p + "</span><div class='mm-trv-sig'>" + s + "</div></div>";
      }).join("");
    }

    function findHeading(rx){
      var els = Array.from(document.querySelectorAll("h1,h2,h3,h4,div,strong,span"));
      return els.find(function(el){
        var t = (el.textContent||"").trim();
        return rx.test(t);
      }) || null;
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

    function removeNoTriggersText(sectionRx){
      // remove any leaf node that says "No buy triggers found." etc.
      var leaves = Array.from(document.querySelectorAll("body *")).filter(function(el){
        return el.childElementCount === 0;
      });
      leaves.forEach(function(el){
        var t = (el.textContent||"").trim();
        if(sectionRx.test(t)) el.textContent = "";
      });
    }

    fetch("/api/trade_review?trade_id=" + encodeURIComponent(trade_id))
      .then(function(res){ return res.ok ? res.json() : Promise.reject("HTTP " + res.status); })
      .then(function(j){
        var buyBox = document.getElementById("mm-trv-buy-box");
        var sellBox = document.getElementById("mm-trv-sell-box");

        if(!buyBox){
          var buyHdr = findHeading(/buy triggers/i);
          if(buyHdr) buyBox = ensureBox("mm-trv-buy-box", buyHdr);
        }
        if(!sellBox){
          var sellHdr = findHeading(/sell triggers/i);
          if(sellHdr) sellBox = ensureBox("mm-trv-sell-box", sellHdr);
        }

        var buyRows = j.buy_triggers || [];
        var sellRows = j.sell_triggers || [];

        if(buyBox){
          buyBox.innerHTML = renderList(buyRows);
          if(buyRows.length) removeNoTriggersText(/^No buy triggers found\.?$/i);
        }
        if(sellBox){
          sellBox.innerHTML = renderList(sellRows);
          if(sellRows.length) removeNoTriggersText(/^No sell triggers found\.?$/i);
        }

        // Fix the "Buy: @ 0.00 | Sell: @ 0.00 | ... | Qty: X" line if present
        var meta = j.meta || {};
        var lines = Array.from(document.querySelectorAll("body *")).filter(function(el){
          return (el.childElementCount===0) && /Buy:\s*@/i.test(el.textContent||"") && /Qty:\s*/i.test(el.textContent||"");
        });

        if(lines.length){
          var el = lines[0];
          var s = el.textContent || "";

          if(meta.anchor_buy_price!=null)  s = s.replace(/Buy:\s*@\s*0\.00/i,  "Buy: @ " + Number(meta.anchor_buy_price).toFixed(2));
          if(meta.anchor_sell_price!=null) s = s.replace(/Sell:\s*@\s*0\.00/i, "Sell: @ " + Number(meta.anchor_sell_price).toFixed(2));
          if(meta.anchor_qty!=null)        s = s.replace(/Qty:\s*[0-9.]+/i,     "Qty: " + meta.anchor_qty);

          el.textContent = s;
        }
      })
      .catch(function(err){
        console.log("%s fetch failed:", err);
      });
  }catch(e){
    console.log("%s exception:", e);
  }
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
""" % (MARK, MARK, MARK, MARK)

# inject before </body> (preferred), else before </html>, else append
low = txt.lower()
if "</body" in low:
    txt2 = re.sub(r"(?is)</body\s*>", block + "\n</body>", txt, count=1)
elif "</html" in low:
    txt2 = re.sub(r"(?is)</html\s*>", block + "\n</html>", txt, count=1)
else:
    txt2 = txt.rstrip() + "\n\n" + block + "\n"

P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
