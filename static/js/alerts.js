// static/js/alerts.js

(function() {
  document.addEventListener('DOMContentLoaded', () => {

    // ----- BUY from Alerts → POST to your simulation buy route -----
    document.querySelectorAll('.buy-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        const row    = btn.closest('tr');
        const symbol = btn.dataset.symbol ||
                       row.querySelector('td:nth-child(2)')?.textContent.trim();
        const qty    = parseInt(row.querySelector('.qty-input')?.value, 10) || 1;

		fetch('/simulation/buy', {
		  method: 'POST',
		  headers: { 'Content-Type': 'application/json' },
		  body: JSON.stringify({ symbol, qty })
		})

        .then(res => {
          if (!res.ok) throw new Error(`buy failed (${res.status})`);
          return res.json();
        })
        .then(() => window.location.reload())
        .catch(err => console.error('Buy error:', err));
      });
    });

    // ----- CLEAR an alert → POST to /clear/<id> -----
    document.querySelectorAll('.clear-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        const id = btn.dataset.id;
        if (!id) return console.error('No alert ID on Clear button');

        fetch(`/clear/${id}`, { method: 'POST' })
          .then(res => {
            if (!res.ok) throw new Error(`clear failed (${res.status})`);
            return res.json();
          })
          .then(() => window.location.reload())
          .catch(err => console.error('Clear error:', err));
      });
    });

  });
})();
