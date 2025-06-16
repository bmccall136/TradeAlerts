// static/js/simulation.js

(function() {
  document.addEventListener('DOMContentLoaded', init);

  function init() {
    // Wire up Buy & Sell buttons
    ['buy', 'sell'].forEach(action => {
      document.querySelectorAll(`.${action}-btn`).forEach(btn => {
        btn.addEventListener('click', e => {
          e.preventDefault();
          const row = btn.closest('tr');
          // Try data-symbol first, then fallback to .symbol-cell or cell index 1
          const symbol = btn.dataset.symbol ||
                         (row.querySelector('.symbol-cell')?.textContent.trim()) ||
                         (row.cells[1]?.textContent.trim() || '');
          // Try data-qty first, then .qty-input, default to 1
          const qty = parseInt(btn.dataset.qty ||
                               row.querySelector('.qty-input')?.value, 10) || 1;
          performAction(action, symbol, qty);
        });
      });
    });

    // Wire up Reset Simulation
    const resetBtn = document.getElementById('reset-simulation-btn');
    if (resetBtn) {
      resetBtn.addEventListener('click', e => {
        e.preventDefault();
        if (confirm('Are you sure you want to reset the simulation?')) {
          fetch('/simulation/reset', { method: 'POST' })
            .then(_ => window.location.reload())
            .catch(err => console.error('Reset failed:', err));
        }
      });
    }
  }

  function performAction(action, symbol, qty) {
    if (!symbol) {
      console.error(`No symbol found for ${action}`);
      return;
    }
    fetch(`/simulation/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, qty })
    })
    .then(res => {
      if (!res.ok) throw new Error(`${action} failed (${res.status})`);
      return res.json();
    })
    .then(() => window.location.reload())
    .catch(err => console.error(`${action} error:`, err));
  }
})();
