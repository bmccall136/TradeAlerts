async function fetchAlerts() {
  const params = new URLSearchParams(window.location.search);
  const filter = params.get('filter') || 'all';
  const res = await fetch(`/api/alerts?filter=${filter}`);
  if (!res.ok) return;
  const data = await res.json();
  const tbody = document.querySelector('#alerts-table tbody');
  tbody.innerHTML = '';
  data.forEach(a => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${ new Date(a.timestamp).toLocaleTimeString() }</td>
      <td><span class="badge badge-light">${ a.filter }</span></td>
      <td>${ a.symbol }</td>
      <td>$${ a.price.toFixed(2) }</td>
      <td>${ a.confidence.toFixed(1) }%</td>
      <td>${ (a.triggers||'').split(',').map(t=>`<span class="badge badge-info mr-1">${t}</span>`).join('') }</td>
      <td><img src="/api/alerts/${a.id}/sparkline.svg" width="100" height="30" /></td>
    `;
    tbody.appendChild(tr);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  fetchAlerts();
  setInterval(fetchAlerts, 5000);
});
