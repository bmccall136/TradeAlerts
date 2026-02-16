/* analytics_sell.js (final)
   - safe fetch (handles non-JSON/500 HTML)
   - removes "Loading ?" by always rendering either data or a clear error
*/
(function(){
  const errBox = document.getElementById('mm-sell-err');

  function showErr(msg){
    if(!errBox) return;
    errBox.style.display = 'block';
    errBox.textContent = msg || 'Unknown error';
  }
  function clearErr(){
    if(!errBox) return;
    errBox.style.display = 'none';
    errBox.textContent = '';
  }

  async function fetchJsonSafe(url){
    const r = await fetch(url, {cache:'no-store'});
    const ct = (r.headers.get('content-type') || '').toLowerCase();
    const txt = await r.text();
    if(!r.ok){
      throw new Error(`HTTP ${r.status}\n${txt.slice(0,2000)}`);
    }
    if(ct.includes('application/json')){
      try { return JSON.parse(txt); }
      catch(e){ throw new Error(`JSON parse failed\n${txt.slice(0,2000)}`); }
    }
    throw new Error(`Non-JSON response\n${txt.slice(0,2000)}`);
  }

  function escapeHtml(s){
    return (s||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  }

  function asPairs(obj){
    if(!obj || typeof obj !== 'object') return [];
    if(Array.isArray(obj)){
      return obj.map(x=>{
        if(x && typeof x === 'object'){
          const k = x.key ?? x.k ?? x.name ?? x.reason ?? x.outcome ?? '';
          const v = x.value ?? x.v ?? x.count ?? x.ct ?? x.n ?? '';
          return [String(k), v];
        }
        return [String(x), ''];
      });
    }
    return Object.keys(obj).map(k => [k, obj[k]]);
  }

  function renderTableInto(el, pairs){
    if(!el) return;
    if(!pairs || !pairs.length){
      el.innerHTML = '<div class="text-secondary small">No data in this bucket.</div>';
      return;
    }
    const rows = pairs
      .sort((a,b)=> (Number(b[1])||0) - (Number(a[1])||0))
      .map(([k,v]) => `<tr><td class="k">${escapeHtml(k)}</td><td class="v">${escapeHtml(String(v))}</td></tr>`)
      .join('');
    el.innerHTML = `<table class="mm-t"><tbody>${rows}</tbody></table>`;
  }

  function setLoading(id, on){
    const el = document.getElementById(id);
    if(el) el.style.display = on ? 'block' : 'none';
  }

  function getParam(name){
    try { return (new URL(window.location.href)).searchParams.get(name) || ''; }
    catch(e){ return ''; }
  }
  function setParam(name, value){
    try{
      const u = new URL(window.location.href);
      if(value) u.searchParams.set(name, value);
      else u.searchParams.delete(name);
      window.history.replaceState({}, '', u.toString());
    }catch(e){}
  }

  function normalizeBucket(b){
    b = (b || 'today').toLowerCase();
    if(b === 'tod') b = 'today';
    if(b === '7') b = '7d';
    if(b === '30') b = '30d';
    return b;
  }

  async function loadSell(bucket){
    clearErr();

    setLoading('mm-exit-loading', true);
    setLoading('mm-outcome-loading', true);
    setLoading('mm-hold-loading', true);

    const date = getParam('date');
    const qs = new URLSearchParams();
    if(bucket) qs.set('bucket', bucket);
    if(date) qs.set('date', date);

    const url = '/api/analytics/sell?' + qs.toString();

    try{
      const j = await fetchJsonSafe(url);

      const reasons  = j.exit_reasons || j.reasons || j.reason_counts || (j.counts && j.counts.exit_reasons) || {};
      const outcomes = j.execution_outcomes || j.outcomes || j.outcome_counts || (j.counts && j.counts.execution_outcomes) || {};
      const holds    = j.hold_buckets || j.hold_time_buckets || j.holds || (j.counts && j.counts.hold_buckets) || {};

      renderTableInto(document.getElementById('mm-exit-box'), asPairs(reasons));
      renderTableInto(document.getElementById('mm-outcome-box'), asPairs(outcomes));
      renderTableInto(document.getElementById('mm-hold-box'), asPairs(holds));
    }catch(e){
      showErr(String(e && e.message ? e.message : e));
      renderTableInto(document.getElementById('mm-exit-box'), []);
      renderTableInto(document.getElementById('mm-outcome-box'), []);
      renderTableInto(document.getElementById('mm-hold-box'), []);
    }finally{
      setLoading('mm-exit-loading', false);
      setLoading('mm-outcome-loading', false);
      setLoading('mm-hold-loading', false);
    }
  }

  const sel = document.getElementById('mm-sell-bucket');
  const initial = normalizeBucket(getParam('bucket') || (sel ? sel.value : 'today'));
  if(sel){
    sel.value = initial;
    sel.addEventListener('change', ()=>{
      const b = normalizeBucket(sel.value);
      setParam('bucket', b);
      loadSell(b);
    });
  }
  loadSell(initial);

  window.addEventListener('error', (ev)=>{
    try{ showErr('JS error: ' + (ev.message || ev.error || 'unknown')); }catch(e){}
  });
  window.addEventListener('unhandledrejection', (ev)=>{
    try{ showErr('Promise rejection: ' + (ev.reason && ev.reason.message ? ev.reason.message : String(ev.reason))); }catch(e){}
  });
})();