document.addEventListener("DOMContentLoaded", function () {
  // BUY button logic
  document.querySelectorAll(".buy-btn").forEach(button => {
    button.addEventListener("click", () => {
      const row = button.closest("tr");
      const symbol = row.querySelector("td:nth-child(2)").textContent.trim();
      const qty = parseInt(row.querySelector(".qty-input").value || "1");

      fetch('/simulation/buy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, qty })
      })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            alert(`Buy order sent for ${symbol} x${qty}`);
            row.remove();  // Now safe — row is defined
          } else {
            alert(`Buy failed: ${data.error}`);
          }
        })
        .catch(err => {
          console.error('Buy error:', err);
          alert('Buy request error.');
        });
    });
  });
});
