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

