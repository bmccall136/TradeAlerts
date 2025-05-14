console.log('🚀 script.js loaded – version 4');

document.addEventListener('DOMContentLoaded', () => {
  const API_ALERTS = '/api/alerts';
  const API_STATUS = '/api/status';
  let currentFilter = 'all';

  // -- Status updater --
  function loadStatus() {
    fetch(API_STATUS)
      .then(r => r.json())
      .then(st => {
        const marketEl = document.querySelector('.status-text.market');
        const etradeEl = document.querySelector('.status-text.etrade');
        if (st.yahoo === 'open') {
          marketEl.textContent = 'Yahoo Finance Intraday: Open';
          marketEl.classList.replace('badge-danger','badge-success');
        } else {
          marketEl.textContent = 'Yahoo Finance Intraday: Market Closed';
          marketEl.classList.replace('badge-success','badge-danger');
        }
        if (st.etrade === 'ok') {
          etradeEl.textContent = 'E*TRADE API: Connected';
          etradeEl.classList.replace('badge-danger','badge-success');
        } else {
          etradeEl.textContent = 'E*TRADE API: Disconnected';
          etradeEl.classList.replace('badge-success','badge-danger');
        }
      })
      .catch(console.error);
  }

  // -- Signal badge helper --
  function badge(type) {
    switch((type||'').toLowerCase()) {
      case 'prime':         return '<span class="signal-prime">💎 Prime</span>';
      case 'sharpshooter':  return '<span class="signal-sharpshooter">🎯 Sharpshooter</span>';
      case 'opportunist':   return '<span class="signal-opportunist">👍 Opportunist</span>';
      case 'sell':          return '<span class="signal-sell">🔥 Sell</span>';
      default:              return '<span class="signal-unknown">?</span>';
    }
  }

  // -- Load alerts into table --
  function loadAlerts() {
    fetch(API_ALERTS)
      .then(r => r.json())
      .then(data => {
        const tbody = document.querySelector('.alerts tbody');
        tbody.innerHTML = '';
        data
          .filter(a => currentFilter==='all' || a.signal.toLowerCase()===currentFilter)
          .forEach(a => {
            const ts = a.timestamp ? a.timestamp.slice(0,19).replace('T',' ') : '--';
            const tr = document.createElement('tr');
           tr.innerHTML = `
  <td>${a.symbol}</td>
  <td>${a.name}</td>
  <td>${badge(a.signal)}</td>
  <td>${typeof a.confidence === 'number' ? Math.round(a.confidence) + '%' : 'N/A'}</td>
  <td>$${parseFloat(a.price).toFixed(2)}</td>
  <td>${ts}</td>
  <td class="sparkline-cell">
    <img src="/sparkline/${a.id}.svg" alt="sparkline" />
  </td>
  <td>${a.vwap ? '$' + parseFloat(a.vwap).toFixed(2) : 'N/A'}</td>
  <td>
    <input type="number" class="qty-input" placeholder="Qty">
    <button class="btn-simulate" data-symbol="${a.symbol}">Buy</button>
  </td>
  <td><button class="btn-clear" data-id="${a.id}">Clear</button></td>`;

            tbody.appendChild(tr);
          });
        document.querySelectorAll('.btn-clear')
                .forEach(btn => btn.onclick = () => fetch(`/alerts/${btn.dataset.id}/clear`,{method:'POST'}).then(loadAlerts));
      })
      .catch(console.error);
  }

  // -- Filter buttons --
  document.querySelectorAll('.filter-btn')
    .forEach(btn => btn.onclick = () => {
      const t = btn.textContent.split(' ')[0].toLowerCase();
      currentFilter = (t==='all'? 'all' : t);
      document.querySelectorAll('.filter-btn').forEach(b=>b.classList.toggle('active',b===btn));
      loadAlerts();
    });

  // Initial load
  loadStatus();
  loadAlerts();
  setInterval(loadStatus, 15000);
  setInterval(loadAlerts, 10000);
});