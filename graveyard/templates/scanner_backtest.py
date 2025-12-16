{% extends "layout.html" %}
{% block content %}
<h2>Scanner Backtest</h2>
<form method="POST" class="mb-4">
  <div>
    <label>Start Date:</label>
    <input type="date" name="start_date" required>
    <label>End Date:</label>
    <input type="date" name="end_date" required>
  </div>
  <div>
    <label>Initial Cash:</label>
    <input type="number" name="initial_cash" value="10000" step="100">
    <label>Max Trade $:</label>
    <input type="number" name="max_trade_per_stock" value="1000" step="50">
  </div>
  <div>
    <label>Trailing Stop %:</label>
    <input type="number" name="trailing_stop_pct" value="0.05" step="0.01">
    <label>Sell After N Days:</label>
    <input type="number" name="sell_after_days">
  </div>
  <div>
    <label><input type="checkbox" name="sma_on" checked> SMA</label>
    <label><input type="checkbox" name="rsi_on" checked> RSI</label>
    <label><input type="checkbox" name="macd_on" checked> MACD</label>
    <label><input type="checkbox" name="bb_on"> BB</label>
    <label><input type="checkbox" name="vwap_on"> VWAP</label>
    <label><input type="checkbox" name="news_on"> News</label>
  </div>
  <button type="submit">Run Backtest</button>
</form>

{% if summary %}
  <h3>Summary</h3>
  <ul>
    <li>Total P/L: ${{ summary.total_pnl }}</li>
    <li>Trades: {{ summary.num_trades }}</li>
    <li>Wins: {{ summary.wins }}</li>
    <li>Losses: {{ summary.losses }}</li>
  </ul>
{% endif %}

{% if trades %}
  <h3>Trades</h3>
  <table>
    <tr>
      <th>Symbol</th><th>Buy Date</th><th>Buy Price</th>
      <th>Sell Date</th><th>Sell Price</th><th>Qty</th><th>P/L</th>
    </tr>
    {% for t in trades %}
    <tr>
      <td>{{ t.symbol }}</td><td>{{ t.buy_date }}</td><td>${{ t.buy_price }}</td>
      <td>{{ t.sell_date }}</td><td>${{ t.sell_price }}</td><td>{{ t.qty }}</td>
      <td>${{ t.pnl }}</td>
    </tr>
    {% endfor %}
  </table>
{% endif %}
{% endblock %}
