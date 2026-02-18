// static/js/analytics_sell_regime.js
(function(){
  function $(id){ return document.getElementById(id); }

  function esc(s){
    return String(s ?? "").replace(/[&<>"']/g, (c)=>({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  async function fetchJson(url){
    const r = await fetch(url, { cache: "no-store" });
    const txt = await r.text();
    if(!r.ok){
      const e = new Error("HTTP " + r.status);
      e.status = r.status;
      e.body = txt;
      throw e;
    }
    try { return JSON.parse(txt); }
    catch(e){
      const x = new Error("Non-JSON response");
      x.body = txt;
      throw x;
    }
  }

  function renderTable(containerId, rows, cols){
    const el = $(containerId);
    if(!el) return;

    if(!rows || !rows.length){
      el.innerHTML = '<div style="opacity:.65;">No data in this bucket.</div>';
      return;
    }

    let th = cols.map(c => `<th style="text-align:${c.align||'left'};">${esc(c.label)}</th>`).join("");
    let tb = rows.map(r => {
      let tds = cols.map(c => {
        let v = (typeof c.get === "function") ? c.get(r) : r[c.key];
        if(v === null || v === undefined) v = "";
        return `<td style="text-align:${c.align||'left'};">${esc(v)}</td>`;
      }).join("");
      return `<tr>${tds}</tr>`;
    }).join("");

    el.innerHTML = `
      <table class="mm-table" style="width:100%; table-layout:fixed;">
        <thead><tr>${th}</tr></thead>
        <tbody>${tb}</tbody>
      </table>
    `;
  }

  function showErr(title, body){
    const wrap = $("mm-sr-error");
    const pre  = $("mm-sr-error-pre");
    if(!wrap || !pre) return;
    wrap.style.display = "block";
    pre.textContent = (title ? String(title) : "Error") + "\n\n" + (body ? String(body) : "");
  }

  function clearErr(){
    const wrap = $("mm-sr-error");
    if(wrap) wrap.style.display = "none";
  }

  async function loadSellRegime(){
    clearErr();

    const bucket = ($("mm-sr-bucket") && $("mm-sr-bucket").value) ? $("mm-sr-bucket").value : "today";
    const meta = $("mm-sr-meta");
    if(meta) meta.textContent = "Loading…";

    try{
      const base = await fetchJson(`/api/analytics/sell_regime?bucket=${encodeURIComponent(bucket)}`);

      if(meta){
        const since = base && base.since_ts_utc ? ("since_ts_utc=" + base.since_ts_utc) : "";
        meta.textContent = `${bucket.toUpperCase()} ${since ? "• " + since : ""}`;
      }

      const regimeRows = base.rows || base.regimes || base.sells_by_regime || [];
      renderTable("mm-sr-regime-table", regimeRows, [
        { key:"regime", label:"Regime" },
        { key:"count",  label:"Count", align:"right", get:(r)=> r.count ?? r.ct ?? r.n ?? "" },
        { key:"avg_conf", label:"Avg Conf", align:"right", get:(r)=> (r.avg_conf ?? r.conf ?? "").toString() }
      ]);

      try{
        const out = await fetchJson(`/api/analytics/sell_regime_outcomes?bucket=${encodeURIComponent(bucket)}`);
        const outRows = out.rows || out.outcomes || [];
        renderTable("mm-sr-outcomes-table", outRows, [
          { key:"regime", label:"Regime" },
          { key:"event",  label:"Event" },
          { key:"count",  label:"Count", align:"right", get:(r)=> r.count ?? r.ct ?? r.n ?? "" }
        ]);
      }catch(e){
        renderTable("mm-sr-outcomes-table", [], []);
      }

      try{
        const rr = await fetchJson(`/api/analytics/sell_regime_reasons?bucket=${encodeURIComponent(bucket)}`);
        const rRows = rr.rows || rr.reasons || [];
        renderTable("mm-sr-reasons-table", rRows, [
          { key:"regime", label:"Regime" },
          { key:"reason", label:"Reason" },
          { key:"count",  label:"Count", align:"right", get:(r)=> r.count ?? r.ct ?? r.n ?? "" }
        ]);
      }catch(e){
        renderTable("mm-sr-reasons-table", [], []);
      }

    }catch(e){
      const body = e && e.body ? e.body : (e && e.stack ? e.stack : String(e));
      showErr("sell_regime failed: " + (e.status ? ("HTTP " + e.status) : ""), body);
      if(meta) meta.textContent = "";
    }
  }

  document.addEventListener("DOMContentLoaded", function(){
    const b = $("mm-sr-bucket");
    if(b) b.addEventListener("change", loadSellRegime);
    loadSellRegime();
  });
})();
