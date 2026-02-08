/* Daily Analytics (DB-backed) - crash-proof renderer */
(function () {
  "use strict";

  // ---------- tiny helpers ----------
  function enc(x) {
    try { return encodeURIComponent(String(x ?? "")); }
    catch (e) { return encodeURIComponent(String(x)); }
  }
  const $  = (sel) => document.querySelector(sel);

  function todayETISO() {
    // YYYY-MM-DD in America/New_York
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    return fmt.format(new Date());
  }

  function shiftISO(iso, days) {
    // iso is YYYY-MM-DD; shift by days safely
    const [y, m, d] = (iso || "").split("-").map(Number);
    if (!y || !m || !d) return iso;
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + (days || 0));
    const y2 = dt.getUTCFullYear();
    const m2 = String(dt.getUTCMonth() + 1).padStart(2, "0");
    const d2 = String(dt.getUTCDate()).padStart(2, "0");
    return `${y2}-${m2}-${d2}`;
  }

  function safeNum(x) {
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
  }

  function fmtMoney(x) {
    const n = safeNum(x);
    if (n === null) return "—";
    // Keep it simple; your CSS controls color
    return (n < 0 ? "-$" + Math.abs(n).toFixed(2) : "$" + n.toFixed(2));
  }

  function fmtPx(x) {
    const n = safeNum(x);
    if (n === null) return "—";
    return "$" + n.toFixed(2);
  }

  function fmtQty(x) {
    const n = safeNum(x);
    if (n === null) return "—";
    // preserve .0 vs int? show int if whole
    return (Math.abs(n - Math.round(n)) < 1e-9) ? String(Math.round(n)) : String(n);
  }

  function fmtPct(x) {
    // backend sometimes gives fraction (0.0031) or null
    const n = safeNum(x);
    if (n === null) return "—";
    return (n * 100).toFixed(2) + "%";
  }

  function setErr(msg) {
    const box = $("#ax-errors");
    if (!box) return;
    box.innerHTML = `<div class="alert alert-danger py-2 mb-0"><b>Analytics error:</b> ${String(msg || "unknown")}</div>`;
  }

  function clearErr() {
    const box = $("#ax-errors");
    if (!box) return;
    box.innerHTML = "";
  }

  function renderList(targetSel, items, kind) {
    const el = $(targetSel);
    if (!el) return;

    if (!Array.isArray(items) || items.length === 0) {
      el.innerHTML = `<div class="text-secondary small">No ${kind} rows.</div>`;
      return;
    }

    // table
    let html = `
      <div class="table-responsive">
      <table class="table table-sm table-dark table-striped align-middle mb-0">
        <thead>
          <tr>
            <th style="white-space:nowrap;">Time (ET)</th>
            <th>Symbol</th>
            <th class="text-end">Qty</th>
            <th class="text-end">Price</th>
            ${kind === "SELL" ? `<th class="text-end">P&amp;L</th><th class="text-end">P&amp;L %</th>` : ``}
            ${kind === "SELL" ? `<th>Reason</th>` : ``}
          </tr>
        </thead>
        <tbody>
    `;

    for (const it of items) {
      try {
        const ts = (it && (it.ts_et || it.time_et || it.ts || "")) || "";
        const sym = (it && (it.symbol || "")) || "";
        const qty = fmtQty(it && it.qty);
        const px  = fmtPx(it && it.price);

        if (kind === "SELL") {
          const pnl = fmtMoney(it && it.gain);
          const pct = fmtPct(it && it.gain_pct);
          const reason = (it && (it.reason || "")) || "";
          html += `
            <tr>
              <td style="white-space:nowrap;">${ts}</td>
              <td><b>${sym}</b></td>
              <td class="text-end">${qty}</td>
              <td class="text-end">${px}</td>
              <td class="text-end">${pnl}</td>
              <td class="text-end">${pct}</td>
              <td>${reason ? reason : ""}</td>
            </tr>
          `;
        } else {
          html += `
            <tr>
              <td style="white-space:nowrap;">${ts}</td>
              <td><b>${sym}</b></td>
              <td class="text-end">${qty}</td>
              <td class="text-end">${px}</td>
            </tr>
          `;
        }
      } catch (rowErr) {
        // keep going even if one row is bad
        console.error("[analytics] row render failed:", rowErr, it);
      }
    }

    html += `</tbody></table></div>`;
    el.innerHTML = html;
  }

  async function loadDay(dateISO) {
    clearErr();

    const iso = (dateISO || "").trim() || todayETISO();
    const dateEl = $("#ax-date");
    if (dateEl) dateEl.textContent = iso;

    const url = `/api/analytics/day?date=${enc(iso)}&cb=${Date.now()}`;

    let data;
    try {
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      data = await resp.json();
    } catch (e) {
      setErr(`Failed to fetch ${url} (${e && e.message ? e.message : e})`);
      renderList("#ax-buy-col", [], "BUY");
      renderList("#ax-sell-col", [], "SELL");
      return;
    }

    if (!data || data.ok !== true) {
      setErr(`API returned ok=false for ${iso}`);
      renderList("#ax-buy-col", [], "BUY");
      renderList("#ax-sell-col", [], "SELL");
      return;
    }

    // counts
    const buyItems  = (data.buy  && Array.isArray(data.buy.items))  ? data.buy.items  : [];
    const sellItems = (data.sell && Array.isArray(data.sell.items)) ? data.sell.items : [];

    const bc = $("#ax-buy-count");
    const sc = $("#ax-sell-count");
    if (bc) bc.textContent = `${buyItems.length} rows`;
    if (sc) sc.textContent = `${sellItems.length} rows`;

    // render
    renderList("#ax-buy-col",  buyItems,  "BUY");
    renderList("#ax-sell-col", sellItems, "SELL");

    // yesterday link
    const y = $("#ax-yesterday");
    if (y) {
      y.onclick = (ev) => {
        ev.preventDefault();
        loadDay(shiftISO(iso, -1));
      };
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const initial = todayETISO();
    loadDay(initial);
  });
})();
