document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".buy-btn").forEach(button => {
    button.addEventListener("click", function () {
      const symbol = this.dataset.symbol;
      const qty = parseInt(document.getElementById("qty").value) || 1;

      fetch("/simulation/buy", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ symbol: symbol, qty: qty })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          alert(`✅ Bought ${qty} share(s) of ${symbol}`);
        } else {
          alert(`❌ Buy failed: ${data.error}`);
        }
      })
      .catch(err => {
        console.error("Buy error:", err);
        alert("Buy request failed.");
      });
    });
  });
});
