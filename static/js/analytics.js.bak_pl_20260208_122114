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
