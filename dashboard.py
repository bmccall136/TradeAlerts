from flask import Flask, render_template, request, redirect, url_for, jsonify
from api import api_bp

from services.alert_service import init_db, clear_alerts_by_filter
from services.simulation_service import (
    get_simulation_state,
    reset_state,
    delete_holding,
    process_trade
)
import yfinance as yf

app = Flask(__name__)
init_db()
app.register_blueprint(api_bp, url_prefix='/api')

@app.route('/alerts')
def alerts_index():
    current_filter = request.args.get('filter', 'all')
    return render_template('alerts.html', current_filter=current_filter)

@app.route('/alerts/clear', methods=['POST'])
def clear_filtered():
    f = request.form.get('filter', 'all')
    clear_alerts_by_filter(f)
    return '', 204

@app.route('/simulation')
def simulation_dashboard():
    state = get_simulation_state()
    holdings = []
    for sym, qty, avg_price in state['holdings']:
        df = yf.Ticker(sym).history(period='1d', interval='1d')
        current_price = df['Close'].iloc[-1] if not df.empty else avg_price
        current_value = qty * current_price
        profit_loss = current_value - (qty * avg_price)
        profit_pct = (profit_loss / (qty * avg_price) * 100) if (qty * avg_price) else 0.0
        holdings.append({
            'symbol': sym,
            'quantity': qty,
            'avg_price': avg_price,
            'current_price': current_price,
            'current_value': current_value,
            'profit_loss': profit_loss,
            'profit_pct': profit_pct
        })

    simulation = {
        'cash':     state['cash'],
        'open':     sum(h['current_value'] for h in holdings),
        'realized': 0.0,
        'holdings': holdings,
        'trades':   state['trades']
    }
    return render_template('simulation.html', simulation=simulation)

@app.route('/simulation/reset', methods=['POST'])
def sim_reset():
    reset_state()
    return redirect(url_for('simulation_dashboard'))

@app.route('/simulation/clear/<symbol>', methods=['POST'])
def clear_holding(symbol):
    delete_holding(symbol)
    return redirect(url_for('simulation_dashboard'))

# ——— NEW ENDPOINT ———
@app.route('/simulation/simulate', methods=['POST'])
def simulate_trade():
    symbol   = request.args.get('symbol', '').upper()
    quantity = int(request.args.get('quantity', 1))
    price    = float(request.args.get('price', 0))
    process_trade(symbol, quantity, price)
    # Return full state so front‑end can optionally re-render without nav away
    state = get_simulation_state()
    return jsonify(state), 200

if __name__ == '__main__':
    app.run(debug=True)
