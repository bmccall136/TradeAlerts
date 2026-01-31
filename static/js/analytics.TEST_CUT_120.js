/* Daily Analytics (DB-backed) - crash-proof renderer */
(function () {
  "use strict";

  function qs(name) {
    try { return new URLSearchParams(window.location.search).get(name); }
    catch { return null; }
  }

  function setText(id, txt) {
    const el = document.getElementById(id);
    if (el) el.textContent = (txt == null ? "" : String(txt));
  }

  function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html || "";
  }

  function enc(x){ return encodeURIComponent(String(x || "")); }

  function tradeReviewUrl(sym, ts_et) {
    // Safe default: dashboard routes usually ignore unknown params
    return `/trade_review?symbol=${enc(sym)}&ts=${enc(ts_et)}`;
  }

  function fmt(x) {
    if (x == null) return "";
    if (typeof x === "number") return Number.isFinite(x) ? x.toFixed(2) : "";
    const s = String(x);
    return s;
  }

  function makeTable(rows, kind) {
    if (!rows || !rows.length) {
      return `<div class="ax-empty">No ${kind.toLowerCase()}s for this day.</div>`;
    }

    // BUY rows: symbol | time ET | reason
    if (kind === "BUY") {
      let out = `<table class="ax-table"><thead><tr>
        <th>Time (ET)</th><th>Symbol</th><th>Reason</th>
      </tr></thead><tbody>`;
      for (const r of rows) {
        const sym = r.symbol || "";
        const ts  = r.ts_et || "";
        const why = r.reason || "";
        const url = tradeReviewUrl(sym, ts);
        out += `<tr>
          <td class="ax-time"><a href="${url}">${ts}</a></td>
          <td class="ax-sym"><a href="${url}">${sym}</a></td>
          <td class="ax-reason">${why}</td>
        </tr>`;
      }
      out += `</tbody></table>`;
      return out;
    }

	// SELL rows: time ET | symbol | price | gain
	function renderSellRowsTable(rows) {
	  let out = `<table class="ax-table"><thead><tr>
		<th>Time (ET)</th><th>Symbol</th><th>Price</th><th>Gain</th>
	  </tr></thead><tbody>`;

	  for (const r of (rows || [])) {
		const sym = r.symbol || "";
		const ts  = r.ts_et || "";
		const url = tradeReviewUrl(sym, ts);

		const price = (r.price == null) ? "" : fmt(r.price);
		const gain  = (r.gain  == null) ? "" : fmt(r.gain);

		// Robustly classify gain even if it arrives as a string
		const gainNum = (r.gain == null)
		  ? null
		  : (typeof r.gain === "number"
			  ? r.gain
			  : parseFloat(String(r.gain).replace(/[^0-9.\-]/g, ""))
			);

		const gainCls = (gainNum == null || Number.isNaN(gainNum))
		  ? ""
		  : (gainNum >= 0 ? "ax-pos" : "ax-neg");

		out += `<tr>
		  <td class="ax-time"><a href="${url}">${ts}</a></td>
		  <td class="ax-sym"><a href="${url}">${sym}</a></td>
		  <td class="ax-num">${price}</td>
		  <td class="ax-num ax-gain ${gainCls}">${gain}</td>
		</tr>`;
	  }

	  out += `</tbody></table>`;
	  return out;
	}

  function etTodayISO() {
    // Use Intl TZ conversion if supported
    try {
      const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year:"numeric", month:"2-digit", day:"2-digit" });
      return fmt.format(new Date()); // YYYY-MM-DD
    } catch {
      // fallback: local date
      const d = new Date();
      const y = d.getFullYear();
      const m = String(d.getMonth()+1).padStart(2,"0");
      const da = String(d.getDate()).padStart(2,"0");
      return `${y}-${m}-${da}`;
    }
  }

  function isoMinusDays(iso, days) {
    try {
      const [y,m,d] = iso.split("-").map(Number);
      const dt = new Date(Date.UTC(y, m-1, d, 12, 0, 0));
      dt.setUTCDate(dt.getUTCDate() - days);
      const yy = dt.getUTCFullYear();
      const mm = String(dt.getUTCMonth()+1).padStart(2,"0");
      const dd = String(dt.getUTCDate()).padStart(2,"0");
      return `${yy}-${mm}-${dd}`;

/* CUT FOR SYNTAX HUNT */
})();
