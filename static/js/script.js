document.addEventListener('DOMContentLoaded', () => {
  let currentFilter = 'all';
  const active = document.querySelector('.filter-btn.btn-success');
  if (active) currentFilter = active.dataset.filter;
  const tbody = document.querySelector('#alerts-table tbody');

  async function fetchAlerts() {
    const res = await fetch(`/api/alerts?filter=${currentFilter}`);
    const alerts = await res.json();
    renderAlerts(alerts);
  }

  function renderAlerts(alerts) {
    tbody.innerHTML = '';
    alerts.forEach(alert => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${new Date(alert.timestamp).toLocaleTimeString()}</td>
        <td>${alert.status}</td>
        <td>${alert.symbol}</td>
        <td>$${alert.price.toFixed(2)}</td>
        <td>${alert.confidence.toFixed(1)}%</td>
        <td>${alert.triggers.split(',').map(t=>`<span class="badge badge-secondary mr-1">${t}</span>`).join('')}</td>
        <td><img src="/api/alerts/${alert.id}/sparkline.svg" alt="spark"></td>
        <td>
          <input type="number" class="qty-input form-control form-control-sm" value="1" min="1"
                 style="width:70px; display:inline-block; margin-right:5px;">
          <button class="btn btn-sm btn-warning clear-btn mr-1" data-id="${alert.id}">Clear</button>
          <button class="btn btn-sm btn-success buy-btn"
                  data-symbol="${alert.symbol}"
                  data-price="${alert.price}">
            Buy
          </button>
        </td>`;
      tbody.appendChild(tr);
    });
    attachHandlers();
  }

  function attachHandlers() {
    // Single‑row clear
    document.querySelectorAll('.clear-btn').forEach(btn => {
      btn.onclick = () => {
        fetch(`/api/alerts/${btn.dataset.id}`, { method: 'DELETE' })
          .then(fetchAlerts);
      };
    });
    // Buy
    document.querySelectorAll('.buy-btn').forEach(btn => {
      btn.onclick = () => {
        const row = btn.closest('tr');
        const qty = parseInt(row.querySelector('.qty-input').value) || 1;
        const sym = btn.dataset.symbol;
        const price = btn.dataset.price;
        fetch(`/simulation/simulate?symbol=${sym}&quantity=${qty}&price=${price}`, {
          method: 'POST'
        })
        .then(res => {
          if (res.ok) window.location.href = '/simulation';
          else console.error('Buy failed', res);
        });
      };
    });
  }

  // Filter buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.onclick = () => {
      currentFilter = btn.dataset.filter;
      document.querySelectorAll('.filter-btn').forEach(b=>b.classList.toggle('btn-success', b===btn));
      fetchAlerts();
    };
  });
  // Clear all
  document.querySelector('#clear-all-btn').onclick = () => {
    fetch(`/api/alerts/clear?filter=${currentFilter}`, { method: 'POST' })
      .then(fetchAlerts);
  };

  fetchAlerts();
  setInterval(fetchAlerts, 5000);
});
