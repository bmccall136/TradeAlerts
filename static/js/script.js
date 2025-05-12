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
        marketEl.textContent = st.yahoo === 'open' ? 'Open' : 'Market Closed';
        marketEl.style.color = st.yahoo === 'open' ? '#4caf50' : '#f44336';
        etradeEl.textContent = st.etrade === 'ok' ? 'Connected' : 'Disconnected';
        etradeEl.style.color = st.etrade === 'ok' ? '#4caf50' : '#f44336';
      })
      .catch(console.error);
  }

  // -- Signal badge helper (explicit cases) --
  function badge(type) {
    switch ((type || '').toLowerCase()) {
      case 'prime':
        return '<span class="signal-prime">💎 Prime</span>';
      case 'sharpshooter':
        return '<span class="signal-sharpshooter">🎯 Sharpshooter</span>';
      case 'opportunist':
        return '<span class="signal-opportunist">👍 Opportunist</span>';
      case 'sell':
        return '<span class="signal-sell">🔥 Sell</span>';
      default:
        return '<span class="signal-unknown">?</span>';
    }
  }

  // -- Load alerts into table with external sparkline SVGs --
  function loadAlerts() {
    fetch(API_ALERTS)
      .then(r => r.json())
      .then(data => {
        const tbody = document.querySelector('.alerts tbody');
        tbody.innerHTML = '';
        data
          .filter(a => currentFilter === 'all' || a.type === currentFilter)
          .forEach(a => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td>${a.symbol}</td>
              <td>${a.name}</td>
              <td>${badge(a.type)}</td>
              <td>${Math.round(a.confidence)}%</td>
              <td>$${parseFloat(a.price).toFixed(2)}</td>
              <td>${a.timestamp}</td>
              <td class="sparkline-cell"><img src="/sparkline/${a.id}.svg" alt="sparkline"/></td>
              <td>${a.triggers.split(',').join(' | ')}</td>
              <td>$${parseFloat(a.vwap).toFixed(2)}</td>
              <td>
                <input type="number" class="qty-input" placeholder="Qty">
                <button class="btn-simulate" data-symbol="${a.symbol}">Buy</button>
              </td>
              <td><button class="btn-clear" data-id="${a.id}">Clear</button></td>`;
            tbody.appendChild(tr);
          });
        // attach clear handlers
        document.querySelectorAll('.btn-clear').forEach(btn => {
          btn.onclick = () => {
            fetch(`/alerts/${btn.dataset.id}/clear`, { method: 'POST' })
              .then(loadAlerts);
          };
        });
      })
      .catch(console.error);
  }

  // -- Filter buttons --
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.onclick = () => {
      const type = btn.textContent.split(' ')[0].toLowerCase();
      currentFilter = type === 'all' ? 'all' : type;
      document.querySelectorAll('.filter-btn')
        .forEach(b => b.classList.toggle('active', b === btn));
      loadAlerts();
    };
  });

  // -- Initial load & polling --
  loadStatus();
  loadAlerts();
  setInterval(loadStatus, 15000);
  setInterval(loadAlerts, 10000);
});
