// analytics.js (Daily Analytics) - $$Machine black theme + Trade Review links
(function(){
  const $ = (sel) => document.querySelector(sel);
  const qs = (k) => (new URLSearchParams(window.location.search).get(k) || "").trim();

  function esc(s){
    return String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function fmt2(n){
    if (n === null || n === undefined || n === "") return "";
    const x = Number(n);
    if (!isFinite(x)) return String(n);
    return x.toFixed(2);
  }
  function fmtPct(n){
    if (n === null || n === undefined || n === "") return "";
    const x = Number(n);
    if (!isFinite(x)) return String(n);
    return (x * 100).toFixed(2) + "%";
  }

  function tradeReviewHref(sym, ts){
    const dateArg = qs("date");
    const href =
      "/trade_review?symbol=" + encodeURIComponent(sym || "") +
      (dateArg ? ("&date=" + encodeURIComponent(dateArg)) : "") +
      (ts ? ("&ts=" + encodeURIComponent(String(ts))) : "");
    return href;
  }

  function renderTable(rows, cols){
    if (!rows || rows.length === 0) {
      return '<div class="text-secondary small">No rows.</div>';
    }

    const thead = cols.map(c =>
      `<th style="
        padding:8px 10px;
        color:#9aa3b2;
        font-size:12px;
        font-weight:600;
        border-bottom:1px solid #222531;
        background:#0b0d12;
        white-space:nowrap;
      ">${esc(c.label)}</th>`
    ).join("");

    const tbody = rows.map(r => {
      const tds = cols.map(c => {
        const v = (c.html ? c.html(r) : esc(c.get(r)));
        return `<td style="
          padding:8px 10px;
          border-top:1px solid #1b1f2a;
          color:#e8e8e8;
          font-size:12.5px;
          vertical-align:middle;
          white-space:nowrap;
        ">${v}</td>`;
      }).join("");
      return `<tr class="mm-rowhover">${tds}</tr>`;
    }).join("");

    return `
      <div style="
        border:1px solid #222531;
        border-radius:10px;
        overflow:hidden;
        background:#0f1118;
      ">
        <style>
          .mm-rowhover:hover td { background:#101726; }
          .mm-scroll { max-height: 680px; overflow:auto; }
          .mm-scroll::-webkit-scrollbar { height:10px; width:10px; }
          .mm-scroll::-webkit-scrollbar-thumb { background:#222531; border-radius:10px; }
        </style>
        <div class="mm-scroll">
          <table style="width:100%; border-collapse:collapse; background:#0f1118;">
            <thead><tr>${thead}</tr></thead>
            <tbody>${tbody}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  async function loadDaily(){
    const dateArg = qs("date");
    const url = "/api/analytics/daily" + (dateArg ? ("?date=" + encodeURIComponent(dateArg)) : "");

    const buyCol  = $("#ax-buy-col");
    const sellCol = $("#ax-sell-col");
    const buyCnt  = $("#ax-buy-count");
    const sellCnt = $("#ax-sell-count");
    const axDate  = $("#ax-date");
    const axErr   = $("#ax-errors");
    const axFiles = $("#ax-files");

    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("API " + res.status + " " + res.statusText);
      const data = await res.json();

      const buys  = data.buys  || [];
      const sells = data.sells || [];

      if (axDate) axDate.textContent = data.date || (dateArg || "");
      if (buyCnt) buyCnt.textContent = buys.length + " rows";
      if (sellCnt) sellCnt.textContent = sells.length + " rows";
      if (axErr) axErr.innerHTML = "";

      if (buyCol){
        buyCol.innerHTML = renderTable(buys, [
          { label: "Time",   get: r => (r.ts || "") },
          { label: "Symbol", html: r => {
              const sym = String(r.symbol || "");
              const href = tradeReviewHref(sym, r.ts);
              return `<a href="${href}" style="color:#00c8ff; text-decoration:none; font-weight:700;">${esc(sym)}</a>`;
            }
          },
          { label: "Name",   get: r => (r.name || "") },
          { label: "Qty",    get: r => (r.qty ?? "") },
          { label: "Price",  get: r => (r.price == null ? "" : fmt2(r.price)) },
        ]);
      }

      if (sellCol){
        sellCol.innerHTML = renderTable(sells, [
          { label: "Time",   get: r => (r.ts || "") },
          { label: "Symbol", html: r => {
              const sym = String(r.symbol || "");
              const href = tradeReviewHref(sym, r.ts);
              return `<a href="${href}" style="color:#00c8ff; text-decoration:none; font-weight:700;">${esc(sym)}</a>`;
            }
          },
          { label: "Name",   get: r => (r.name || "") },
          { label: "Qty",    get: r => (r.qty ?? "") },
          { label: "Open",   get: r => (r.open_price == null ? "" : fmt2(r.open_price)) },
          { label: "Close",  get: r => (r.close_price == null ? "" : fmt2(r.close_price)) },
          { label: "P/L",    get: r => (r.gain == null ? "" : fmt2(r.gain)) },
          { label: "P/L %",  get: r => (r.gain_pct == null ? "" : fmtPct(r.gain_pct)) },
        ]);
      }

      if (axFiles) axFiles.textContent =
        "Source: position_opened (buys) + realized_trades (sells)  |  API: " + url;

    } catch (e) {
      if (axErr) axErr.innerHTML =
        `<div class="alert alert-danger py-2 mb-0"><b>Daily Analytics failed:</b> ${esc(e.message || e)}</div>`;
      if (buyCol) buyCol.textContent = "No BUY rows.";
      if (sellCol) sellCol.textContent = "No SELL rows.";
      if (buyCnt) buyCnt.textContent = "0 rows";
      if (sellCnt) sellCnt.textContent = "0 rows";
    }
  }

  document.addEventListener("DOMContentLoaded", loadDaily);
})();


;/* MM_PL_COLORIZE_V1 */
(function(){
  function _mmNorm(s){ return String(s||"").replace(/\s+/g," ").trim().toLowerCase(); }
  function _mmNum(s){
    var x = String(s||"").replace(/[$,%\s]/g,"").replace(/,/g,"");
    var v = parseFloat(x);
    return isFinite(v) ? v : NaN;
  }
  function _mmPaint(td, v){
    if (!td) return;
    td.classList.remove("pl-pos","pl-neg","pl-zero");
    if (!isFinite(v) || v === 0) td.classList.add("pl-zero");
    else if (v > 0) td.classList.add("pl-pos");
    else td.classList.add("pl-neg");
  }

  function _mmColorizeTables(){
    document.querySelectorAll("table").forEach(function(tbl){
      var ths = Array.from(tbl.querySelectorAll("thead th"));
      if (!ths.length) return;

      var idxPL = -1, idxPLP = -1;
      ths.forEach(function(th,i){
        var t = _mmNorm(th.textContent);
        if (t === "p/l" || t === "pl" || t === "p&l") idxPL = i;
        if (t === "p/l %" || t === "pl %" || t === "p&l %") idxPLP = i;
      });

      if (idxPL < 0 && idxPLP < 0) return;

      Array.from(tbl.querySelectorAll("tbody tr")).forEach(function(tr){
        var tds = tr.querySelectorAll("td");
        if (idxPL >= 0 && tds[idxPL])   _mmPaint(tds[idxPL],  _mmNum(tds[idxPL].textContent));
        if (idxPLP >= 0 && tds[idxPLP]) _mmPaint(tds[idxPLP], _mmNum(tds[idxPLP].textContent));
      });
    });
  }

  // Call now, and keep repainting after your JS renders tables
  function _mmKick(){
    try { _mmColorizeTables(); } catch(e) {}
  }

  // Run once the page is ready
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _mmKick);
  else _mmKick();

  // Re-run after async XHR/table rebuilds (this is the key)
  setTimeout(_mmKick, 200);
  setTimeout(_mmKick, 600);
  setTimeout(_mmKick, 1200);

  // And if DOM changes later, repaint
  try {
    var mo = new MutationObserver(function(){ _mmKick(); });
    mo.observe(document.documentElement, {subtree:true, childList:true});
  } catch(e) {}
})();



;/* MM_PL_COLORIZE_FORCE_V2 */
(function(){
  function norm(s){ return String(s||"").replace(/\s+/g," ").trim().toLowerCase(); }
  function num(s){
    var x = String(s||"").replace(/[$,%\s]/g,"").replace(/,/g,"");
    var v = parseFloat(x);
    return isFinite(v) ? v : NaN;
  }
  function paint(td, v){
    if (!td) return;
    td.classList.remove("pl-pos","pl-neg","pl-zero");
    td.style.fontWeight = "800";
    if (!isFinite(v) || v === 0) {
      td.classList.add("pl-zero");
      td.style.color = "#9e9e9e";
    } else if (v > 0) {
      td.classList.add("pl-pos");
      td.style.color = "#00e676";
    } else {
      td.classList.add("pl-neg");
      td.style.color = "#ff5252";
    }
  }

  function colorize(){
    document.querySelectorAll("table").forEach(function(tbl){
      var ths = Array.from(tbl.querySelectorAll("thead th"));
      if (!ths.length) return;

      var idxPL=-1, idxPLP=-1;
      ths.forEach(function(th,i){
        var t = norm(th.textContent);
        if (t === "p/l" || t === "pl" || t === "p&l") idxPL = i;
        if (t === "p/l %" || t === "pl %" || t === "p&l %") idxPLP = i;
      });
      if (idxPL < 0 && idxPLP < 0) return;

      Array.from(tbl.querySelectorAll("tbody tr")).forEach(function(tr){
        var tds = tr.querySelectorAll("td");
        if (idxPL  >= 0 && tds[idxPL])  paint(tds[idxPL],  num(tds[idxPL].textContent));
        if (idxPLP >= 0 && tds[idxPLP]) paint(tds[idxPLP], num(tds[idxPLP].textContent));
      });
    });
  }

  function kick(){ try { colorize(); } catch(e) {} }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", kick);
  else kick();

  // repaint after async render
  setTimeout(kick, 150);
  setTimeout(kick, 400);
  setTimeout(kick, 900);
  setTimeout(kick, 1500);

  try {
    var mo = new MutationObserver(function(){ kick(); });
    mo.observe(document.documentElement, {subtree:true, childList:true});
  } catch(e) {}
})();





/* MM_ANALYTICS_SIGNAL_FIRES_POLISH_V1_START */
(function(){
  function mmInjectPolishCSS(){
    if (document.getElementById("mm-analytics-polish-css-v1")) return;
    var css = `
      /* Scoped: only tables we mark with .mm-polish-fires */
      table.mm-polish-fires { border-collapse: separate; border-spacing: 0; }
      table.mm-polish-fires tbody tr:nth-child(odd){ background: rgba(255,255,255,0.02); }
      table.mm-polish-fires tbody tr:hover{ background: rgba(255,215,0,0.06); }
      table.mm-polish-fires td, table.mm-polish-fires th { border-color: rgba(255,255,255,0.08) !important; }
      .mm-ind-wrap{ display:flex; align-items:center; gap:10px; }
      .mm-ind-dot{ width:10px; height:10px; border-radius:999px; box-shadow: 0 0 0 2px rgba(0,0,0,0.55); flex:0 0 auto; }
      .mm-ind-ico{ width:14px; height:14px; display:inline-flex; align-items:center; justify-content:center; opacity:.95; flex:0 0 auto; }
      .mm-ind-key{ font-weight:600; letter-spacing:.2px; }
      .mm-ind-sub{ font-size:11px; opacity:.7; margin-left:4px; }
      .mm-ind-ico svg{ width:14px; height:14px; display:block; }
    `;
    var style = document.createElement("style");
    style.id = "mm-analytics-polish-css-v1";
    style.textContent = css;
    document.head.appendChild(style);
  }

  var META = {
    sma:  { color:"#66a3ff", label:"SMA",  svg:'<path d="M4 12h4l2-6 2 10 2-4h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' },
    vwap: { color:"#21d0c3", label:"VWAP", svg:'<path d="M4 17l4-6 4 3 4-7 4 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' },
    macd: { color:"#b48cff", label:"MACD", svg:'<path d="M4 16c2-6 4-9 8-9s6 3 8 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    vol:  { color:"#ffb84d", label:"VOL",  svg:'<path d="M6 18V10M10 18V6M14 18v-8M18 18v-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    rsi:  { color:"#7dff8a", label:"RSI",  svg:'<path d="M4 14c2 0 2-6 4-6s2 8 4 8 2-10 4-10 2 8 4 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    bb:   { color:"#ff6ad5", label:"BB",   svg:'<path d="M6 6v12M18 6v12M9 10h6M9 14h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' }
  };

  function mmFindSignalFiresTable(){
    // Find a card whose header contains "Signal Fires" then grab the first table inside it.
    var cards = document.querySelectorAll(".card, .mm-ax-card, .card-body");
    for (var i=0;i<cards.length;i++){
      var el = cards[i];
      var txt = (el.textContent || "").toLowerCase();
      if (txt.indexOf("signal fires") !== -1){
        var t = el.querySelector("table");
        if (t) return t;
      }
    }
    // fallback: any table that has columns "Indicator" and "Fires"
    var tables = document.querySelectorAll("table");
    for (var j=0;j<tables.length;j++){
      var th = tables[j].querySelectorAll("th");
      if (!th || th.length < 2) continue;
      var a = (th[0].textContent||"").toLowerCase().trim();
      var b = (th[1].textContent||"").toLowerCase().trim();
      if (a === "indicator" && (b === "fires" || b.indexOf("fire") !== -1)) return tables[j];
    }
    return null;
  }

  function mmDecorate(){
    mmInjectPolishCSS();
    var t = mmFindSignalFiresTable();
    if (!t) return false;

    if (!t.classList.contains("mm-polish-fires")) t.classList.add("mm-polish-fires");

    var rows = t.querySelectorAll("tbody tr");
    for (var i=0;i<rows.length;i++){
      var tr = rows[i];
      if (tr.getAttribute("data-mm-polished") === "1") continue;
      var td0 = tr.querySelector("td");
      if (!td0) continue;

      var key = (td0.textContent || "").trim().toLowerCase();
      // normalize common variants
      if (key === "volume") key = "vol";
      var m = META[key] || { color:"#888", label:key.toUpperCase(), svg:'<path d="M6 12h12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' };

      td0.textContent = "";
      var wrap = document.createElement("div");
      wrap.className = "mm-ind-wrap";

      var dot = document.createElement("span");
      dot.className = "mm-ind-dot";
      dot.style.background = m.color;

      var ico = document.createElement("span");
      ico.className = "mm-ind-ico";
      ico.style.color = m.color;
      ico.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + m.svg + '</svg>';

      var keySpan = document.createElement("span");
      keySpan.className = "mm-ind-key";
      keySpan.textContent = key;

      var sub = document.createElement("span");
      sub.className = "mm-ind-sub";
      sub.textContent = m.label;

      wrap.appendChild(dot);
      wrap.appendChild(ico);
      wrap.appendChild(keySpan);
      wrap.appendChild(sub);

      td0.appendChild(wrap);
      tr.setAttribute("data-mm-polished","1");
    }
    return true;
  }

  function mmStart(){
    // Try immediately, then retry a few times (tables often render async)
    var tries = 0;
    var iv = setInterval(function(){
      tries++;
      if (mmDecorate() || tries >= 20) clearInterval(iv);
    }, 250);

    // Also watch for table re-render (source/bucket changes)
    try{
      var mo = new MutationObserver(function(){
        mmDecorate();
      });
      mo.observe(document.body, { childList:true, subtree:true });
    } catch(e){}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mmStart);
  } else {
    mmStart();
  }
})();
/* MM_ANALYTICS_SIGNAL_FIRES_POLISH_V1_END */


/* MM_ANALYTICS_POLISH_V1_START */
(function(){
  function mmInjectPolishCSS(){
    if (document.getElementById("mm-analytics-polish-css-v1")) return;

    var css = `
      /* --- Scoped cosmetics (analytics pages only) --- */
      .mm-polish-pill{
        display:inline-flex; align-items:center; gap:6px;
        padding:3px 10px; border-radius:999px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.10);
        font-size: 12px; opacity: .92;
      }

      /* Signal Fires table polish */
      table.mm-polish-fires { border-collapse: separate; border-spacing: 0; }
      table.mm-polish-fires tbody tr:nth-child(odd){ background: rgba(255,255,255,0.018); }
      table.mm-polish-fires tbody tr:hover{ background: rgba(255,215,0,0.055); transition: background 120ms ease; }
      table.mm-polish-fires td, table.mm-polish-fires th { border-color: rgba(255,255,255,0.08) !important; }
      table.mm-polish-fires thead th{
        color: rgba(255,255,255,0.92);
      }

      .mm-ind-wrap{ display:flex; align-items:center; gap:10px; }
      .mm-ind-dot{
        width:10px; height:10px; border-radius:999px;
        box-shadow: 0 0 0 2px rgba(0,0,0,0.55);
        flex:0 0 auto;
      }
      .mm-ind-ico{
        width:14px; height:14px; display:inline-flex;
        align-items:center; justify-content:center;
        opacity:.95; flex:0 0 auto;
      }
      .mm-ind-ico svg{ width:14px; height:14px; display:block; }
      .mm-ind-key{ font-weight:700; letter-spacing:.2px; }
      .mm-ind-sub{ font-size:11px; opacity:.7; margin-left:4px; }

      /* Card header accent (Signal Fires) */
      .mm-polish-sf-header{
        position: relative;
        padding-left: 14px;
      }
      .mm-polish-sf-header:before{
        content:"";
        position:absolute; left:0; top:2px; bottom:2px;
        width:3px; border-radius:3px;
        background: rgba(255,215,0,0.85);
        box-shadow: 0 0 10px rgba(255,215,0,0.18);
      }

      /* Make the active analytics tab feel "active" */
      .mm-ax-nav a.mm-polish-active,
      .mm-ax-nav button.mm-polish-active{
        border-color: rgba(255,215,0,0.9) !important;
        box-shadow: 0 0 0 1px rgba(255,215,0,0.25), 0 0 14px rgba(255,215,0,0.10);
      }

      /* Regime badge dot pulse (subtle) */
      .mm-regime-dot.mm-polish-pulse{
        animation: mmPulse 1.8s ease-in-out infinite;
      }
      @keyframes mmPulse{
        0%{ transform: scale(1); opacity: .9; }
        50%{ transform: scale(1.15); opacity: 1; }
        100%{ transform: scale(1); opacity: .9; }
      }
    `;

    var style = document.createElement("style");
    style.id = "mm-analytics-polish-css-v1";
    style.textContent = css;
    document.head.appendChild(style);
  }

  var META = {
    sma:  { color:"#66a3ff", label:"SMA",  svg:'<path d="M4 12h4l2-6 2 10 2-4h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' },
    vwap: { color:"#21d0c3", label:"VWAP", svg:'<path d="M4 17l4-6 4 3 4-7 4 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' },
    macd: { color:"#b48cff", label:"MACD", svg:'<path d="M4 16c2-6 4-9 8-9s6 3 8 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    vol:  { color:"#ffb84d", label:"VOL",  svg:'<path d="M6 18V10M10 18V6M14 18v-8M18 18v-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    rsi:  { color:"#7dff8a", label:"RSI",  svg:'<path d="M4 14c2 0 2-6 4-6s2 8 4 8 2-10 4-10 2 8 4 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' },
    bb:   { color:"#ff6ad5", label:"BB",   svg:'<path d="M6 6v12M18 6v12M9 10h6M9 14h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' }
  };

  function mmFindSignalFiresCard(){
    // Find the closest container that contains the "Signal Fires" title
    var nodes = document.querySelectorAll("body *");
    for (var i=0;i<nodes.length;i++){
      var el = nodes[i];
      if (!el || !el.textContent) continue;
      var t = el.textContent.trim();
      if (t === "Signal Fires"){
        return el.closest(".card") || el.parentElement || null;
      }
    }
    return null;
  }

  function mmFindSignalFiresTable(){
    var card = mmFindSignalFiresCard();
    if (card){
      var table = card.querySelector("table");
      if (table) return table;
    }
    // fallback: any table with th "Indicator" and "Fires"
    var tables = document.querySelectorAll("table");
    for (var j=0;j<tables.length;j++){
      var th = tables[j].querySelectorAll("th");
      if (!th || th.length < 2) continue;
      var a = (th[0].textContent||"").toLowerCase().trim();
      var b = (th[1].textContent||"").toLowerCase().trim();
      if (a === "indicator" && (b === "fires" || b.indexOf("fire") !== -1)) return tables[j];
    }
    return null;
  }

  function mmPolishSignalFires(){
    var card = mmFindSignalFiresCard();
    var table = mmFindSignalFiresTable();
    if (!table) return false;

    // Mark table for scoped CSS
    if (!table.classList.contains("mm-polish-fires")) table.classList.add("mm-polish-fires");

    // Add header accent if we can locate the title node
    if (card){
      // find the element whose text is exactly "Signal Fires" and decorate its container
      var titleEl = null;
      var cand = card.querySelectorAll("*");
      for (var k=0;k<cand.length;k++){
        if ((cand[k].textContent||"").trim() === "Signal Fires"){ titleEl = cand[k]; break; }
      }
      if (titleEl && titleEl.parentElement && !titleEl.parentElement.classList.contains("mm-polish-sf-header")){
        titleEl.parentElement.classList.add("mm-polish-sf-header");
      }
    }

    // Convert "Rows: ... ? Bucket: ..." into pills
    if (card){
      var metaNode = null;
      var all = card.querySelectorAll("*");
      for (var m=0;m<all.length;m++){
        var txt = (all[m].textContent||"").trim();
        if (txt.startsWith("Rows:") && txt.indexOf("Bucket:") !== -1){
          metaNode = all[m];
          break;
        }
      }
      if (metaNode && !metaNode.getAttribute("data-mm-pillified")){
        var txt = (metaNode.textContent||"").trim();
        // naive parse: "Rows: 188318 ? Bucket: 7d"
        var rows = "";
        var bucket = "";
        try{
          var parts = txt.split("?").map(function(x){ return x.trim(); });
          for (var z=0;z<parts.length;z++){
            if (parts[z].toLowerCase().startsWith("rows:")) rows = parts[z].split(":")[1].trim();
            if (parts[z].toLowerCase().startsWith("bucket:")) bucket = parts[z].split(":")[1].trim().toUpperCase();
          }
        } catch(e){}
        metaNode.textContent = "";
        var pill1 = document.createElement("span");
        pill1.className = "mm-polish-pill";
        pill1.textContent = (rows ? rows : "0") + " Rows";
        var pill2 = document.createElement("span");
        pill2.className = "mm-polish-pill";
        pill2.textContent = (bucket ? bucket : "");
        metaNode.appendChild(pill1);
        metaNode.appendChild(document.createTextNode(" "));
        metaNode.appendChild(pill2);
        metaNode.setAttribute("data-mm-pillified","1");
      }
    }

    // Decorate indicator cells with dot + icon
    var rows = table.querySelectorAll("tbody tr");
    for (var r=0;r<rows.length;r++){
      var tr = rows[r];
      if (tr.getAttribute("data-mm-polished") === "1") continue;
      var td0 = tr.querySelector("td");
      if (!td0) continue;

      var key = (td0.textContent || "").trim().toLowerCase();
      if (key === "volume") key = "vol";
      var mta = META[key] || { color:"#888", label:key.toUpperCase(), svg:'<path d="M6 12h12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' };

      td0.textContent = "";
      var wrap = document.createElement("div");
      wrap.className = "mm-ind-wrap";

      var dot = document.createElement("span");
      dot.className = "mm-ind-dot";
      dot.style.background = mta.color;

      var ico = document.createElement("span");
      ico.className = "mm-ind-ico";
      ico.style.color = mta.color;
      ico.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + mta.svg + '</svg>';

      var keySpan = document.createElement("span");
      keySpan.className = "mm-ind-key";
      keySpan.textContent = key;

      var sub = document.createElement("span");
      sub.className = "mm-ind-sub";
      sub.textContent = mta.label;

      wrap.appendChild(dot);
      wrap.appendChild(ico);
      wrap.appendChild(keySpan);
      wrap.appendChild(sub);

      td0.appendChild(wrap);
      tr.setAttribute("data-mm-polished","1");
    }

    return true;
  }

  function mmPolishActiveTab(){
    // Mark the correct analytics tab as active-glow (without changing templates)
    var path = (window.location.pathname || "").toLowerCase();
    var want = null;
    if (path.indexOf("/analytics/buy_regime") !== -1) want = "buy regime";
    else if (path.indexOf("/analytics/sell_regime") !== -1) want = "sell regime";
    else if (path.indexOf("/analytics/buy") !== -1) want = "buy analytics";
    else if (path.indexOf("/analytics/sell") !== -1) want = "sell analytics";
    else if (path.indexOf("/analytics") !== -1) want = "daily";

    if (!want) return;

    // Common containers: .mm-ax-nav (your toolbar row)
    var nav = document.querySelector(".mm-ax-nav") || document;
    var items = nav.querySelectorAll("a,button");
    for (var i=0;i<items.length;i++){
      var t = (items[i].textContent||"").trim().toLowerCase();
      if (t === want){
        items[i].classList.add("mm-polish-active");
      } else {
        items[i].classList.remove("mm-polish-active");
      }
    }
  }

  function mmPolishRegimeDot(){
    // If a regime dot exists, give it a subtle pulse
    var dot = document.querySelector(".mm-regime-dot");
    if (dot) dot.classList.add("mm-polish-pulse");
  }

  function mmRun(){
    mmInjectPolishCSS();
    mmPolishActiveTab();
    mmPolishRegimeDot();
    mmPolishSignalFires();
  }

  function mmStart(){
    var tries = 0;
    var iv = setInterval(function(){
      tries++;
      mmRun();
      if (tries >= 30) clearInterval(iv);
    }, 250);

    try{
      var mo = new MutationObserver(function(){ mmRun(); });
      mo.observe(document.body, { childList:true, subtree:true });
    } catch(e){}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mmStart);
  } else {
    mmStart();
  }
})();
/* MM_ANALYTICS_POLISH_V1_END */




/* MM_ANALYTICS_POLISH_V3_START */
(function(){
  function injectCSS(){
    if (document.getElementById("mm-polish-v3")) return;
    var css = `
      .mm-sf-accent{ position:relative; padding-left:16px; }
      .mm-sf-accent:before{
        content:""; position:absolute; left:0; top:4px; bottom:4px; width:3px;
        border-radius:3px; background:#ffd700; box-shadow:0 0 10px rgba(255,215,0,0.2);
      }

      table.mm-sf-table tbody tr:nth-child(odd){ background:rgba(255,255,255,0.02); }
      table.mm-sf-table tbody tr:hover{ background:rgba(255,215,0,0.06); transition:background 120ms ease; }
      table.mm-sf-table th, table.mm-sf-table td{ border-color:rgba(255,255,255,0.08)!important; }

      .mm-dot{
        width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:10px;
        box-shadow:0 0 0 2px rgba(0,0,0,0.6);
      }

      .mm-pill{
        display:inline-block; padding:4px 10px; border-radius:999px;
        background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
        font-size:12px; margin-right:6px;
      }

      .mm-ax-nav a.mm-active-polish,
      .mm-ax-nav button.mm-active-polish{
        border-color:#ffd700!important;
        box-shadow:0 0 12px rgba(255,215,0,0.15);
      }

      .mm-regime-dot.mm-pulse{ animation:mmPulse 1.8s ease-in-out infinite; }
      @keyframes mmPulse{ 0%{transform:scale(1)} 50%{transform:scale(1.12)} 100%{transform:scale(1)} }
    `;
    var style=document.createElement("style");
    style.id="mm-polish-v3";
    style.textContent=css;
    document.head.appendChild(style);
  }

  var COLORS = { sma:"#66a3ff", vwap:"#21d0c3", macd:"#b48cff", vol:"#ffb84d", rsi:"#7dff8a", bb:"#ff6ad5" };

  function findSignalFiresCard(){
    var els = document.querySelectorAll("body *");
    for (var i=0;i<els.length;i++){
      if ((els[i].textContent||"").trim() === "Signal Fires"){
        return els[i].closest(".card") || els[i].parentElement || null;
      }
    }
    return null;
  }

  function polishSignalFires(){
    var card = findSignalFiresCard();
    if (!card) return false;

    if (!card.classList.contains("mm-sf-accent")) card.classList.add("mm-sf-accent");

    var table = card.querySelector("table");
    if (!table) return false;

    if (!table.classList.contains("mm-sf-table")) table.classList.add("mm-sf-table");

    var rows = table.querySelectorAll("tbody tr");
    for (var r=0;r<rows.length;r++){
      var tr = rows[r];
      if (tr.dataset.mmPolished === "1") continue;
      var td = tr.querySelector("td");
      if (!td) continue;
      var key = (td.textContent||"").trim().toLowerCase();
      if (key === "volume") key = "vol";
      var color = COLORS[key] || "#888";
      td.innerHTML = '<span class="mm-dot" style="background:'+color+'"></span>' + key;
      tr.dataset.mmPolished = "1";
    }
    return true;
  }

  function polishMetaPills(){
    var nodes = document.querySelectorAll("body *");
    for (var i=0;i<nodes.length;i++){
      var el = nodes[i];
      if (!el || el.dataset.mmPilled === "1") continue;
      var txt = (el.textContent||"").trim();
      if (!txt.startsWith("Rows:") || txt.indexOf("Bucket:") === -1) continue;

      // Example: "Rows: 188318 ? Bucket: 7d"
      var parts = txt.split("?").map(function(x){ return (x||"").trim(); });
      var rowsVal="", bucketVal="";
      for (var j=0;j<parts.length;j++){
        var p = parts[j].toLowerCase();
        if (p.startsWith("rows:")) rowsVal = parts[j].split(":")[1].trim();
        if (p.startsWith("bucket:")) bucketVal = parts[j].split(":")[1].trim().toUpperCase();
      }
      el.innerHTML =
        '<span class="mm-pill">'+(rowsVal||"0")+' Rows</span>' +
        '<span class="mm-pill">'+(bucketVal||"")+'</span>';
      el.dataset.mmPilled="1";
    }
  }

  function polishActiveTab(){
    var path=(location.pathname||"").toLowerCase();
    var target=null;
    if (path.indexOf("buy_regime")!==-1) target="buy regime";
    else if (path.indexOf("sell_regime")!==-1) target="sell regime";
    else if (path.indexOf("/analytics/buy")!==-1) target="buy analytics";
    else if (path.indexOf("/analytics/sell")!==-1) target="sell analytics";
    else if (path.indexOf("/analytics")!==-1) target="daily";

    var nav=document.querySelector(".mm-ax-nav");
    if (!nav || !target) return;

    var items = nav.querySelectorAll("a,button");
    for (var i=0;i<items.length;i++){
      var t=(items[i].textContent||"").trim().toLowerCase();
      if (t===target) items[i].classList.add("mm-active-polish");
      else items[i].classList.remove("mm-active-polish");
    }
  }

  function polishRegime(){
    var dot=document.querySelector(".mm-regime-dot");
    if (dot) dot.classList.add("mm-pulse");
  }

  function run(){
    try{
      injectCSS();
      polishActiveTab();
      polishRegime();
      polishSignalFires();
      polishMetaPills();
    } catch(e){
      // swallow: never break analytics
    }
  }

  function start(){
    var tries=0;
    var iv=setInterval(function(){
      tries++;
      run();
      if (tries>=40) clearInterval(iv);
    }, 250);

    try{
      var mo=new MutationObserver(function(){ run(); });
      mo.observe(document.body,{childList:true,subtree:true});
    }catch(e){}
  }

  if (document.readyState==="loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
/* MM_ANALYTICS_POLISH_V3_END */

